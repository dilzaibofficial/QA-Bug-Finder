from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db, is_user_verified
import config

import stripe
stripe.api_key = config.STRIPE_SECRET_KEY

billing_bp = Blueprint("billing", __name__)

FRONTEND_URL = "http://localhost:3000"

# Prices are the literal figures requested: 20 / 40 / 100 (USD), with a
# Pakistani-Rupee equivalent for PK users. Both are real Stripe presentment
# currencies — verified against this account before shipping.
PLANS = {
    "3m" : {"key": "3m",  "label": "3 Months", "months": 3,  "usd": 20,  "pkr": 5500},
    "6m" : {"key": "6m",  "label": "6 Months", "months": 6,  "usd": 40,  "pkr": 11000},
    "12m": {"key": "12m", "label": "1 Year",   "months": 12, "usd": 100, "pkr": 28000},
}

CURRENCY_BY_COUNTRY = {"PK": "pkr"}  # everything else falls back to usd
CURRENCY_SYMBOL = {"usd": "$", "pkr": "Rs "}


def _currency_for(country):
    return CURRENCY_BY_COUNTRY.get((country or "").upper(), "usd")


def _user_or_none(db, user_id):
    from bson import ObjectId
    try:
        return db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def _activate_subscription(db, user_id, plan_key, currency, amount, session_id=None):
    from bson import ObjectId
    now = datetime.utcnow()
    plan = PLANS[plan_key]
    expires = now + timedelta(days=30 * plan["months"])

    db.subscriptions.update_one(
        {"stripe_session_id": session_id} if session_id else {"_id": None},
        {
            "$set": {
                "user_id"          : user_id,
                "plan"             : plan_key,
                "currency"         : currency,
                "amount"           : amount,
                "stripe_session_id": session_id,
                "started_at"       : now.isoformat(),
                "expires_at"       : expires.isoformat(),
                "status"           : "active",
            }
        },
        upsert=True,
    )
    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_verified": True}})
    return expires


# ── GET /api/billing/plans?country=xx ─────────────────────────────────────────
@billing_bp.route("/plans", methods=["GET"])
def get_plans():
    country  = request.args.get("country", "")
    currency = _currency_for(country)
    plans = [
        {
            "key"     : p["key"],
            "label"   : p["label"],
            "months"  : p["months"],
            "price"   : p[currency],
            "currency": currency,
            "symbol"  : CURRENCY_SYMBOL[currency],
        }
        for p in PLANS.values()
    ]
    return jsonify({"plans": plans, "currency": currency}), 200


# ── GET /api/billing/status?user_id=xxx ───────────────────────────────────────
@billing_bp.route("/status", methods=["GET"])
def get_status():
    user_id = request.args.get("user_id")
    db = get_db()
    subscribed = is_user_verified(db, user_id)
    sub = None
    if subscribed:
        sub = db.subscriptions.find_one({"user_id": user_id, "status": "active"}, sort=[("expires_at", -1)])
    return jsonify({
        "subscribed": subscribed,
        "plan"      : sub["plan"] if sub else None,
        "expires_at": sub["expires_at"] if sub else None,
    }), 200


# ── POST /api/billing/create-checkout-session ─────────────────────────────────
@billing_bp.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        data     = request.get_json() or {}
        user_id  = data.get("user_id")
        plan_key = data.get("plan")
        country  = data.get("country", "")

        if plan_key not in PLANS:
            return jsonify({"error": "Invalid plan"}), 400

        db   = get_db()
        user = _user_or_none(db, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        plan     = PLANS[plan_key]
        currency = _currency_for(country)
        amount   = plan[currency]

        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            customer_email=user.get("email"),
            line_items=[{
                "price_data": {
                    "currency": currency,
                    "unit_amount": int(round(amount * 100)),
                    "product_data": {
                        "name": f"Bug Plus — {plan['label']}",
                        "description": "Unlimited projects + Claude AI enhanced analysis",
                    },
                },
                "quantity": 1,
            }],
            metadata={"user_id": user_id, "plan": plan_key, "country": country, "currency": currency},
            success_url=f"{FRONTEND_URL}/bug-plus?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/bug-plus?checkout=cancelled",
        )

        # Pending record so the dashboard has something to reconcile even if
        # the user never comes back to trigger verify-session.
        db.subscriptions.insert_one({
            "user_id"          : user_id,
            "plan"             : plan_key,
            "currency"         : currency,
            "amount"           : amount,
            "stripe_session_id": session.id,
            "status"           : "pending",
            "created_at"       : datetime.utcnow().isoformat(),
        })

        return jsonify({"url": session.url}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── GET /api/billing/verify-session?session_id=&user_id= ─────────────────────
# Called when Stripe redirects back to /bug-plus after checkout. No webhook
# needed for local dev — we just ask Stripe directly whether it was paid.
@billing_bp.route("/verify-session", methods=["GET"])
def verify_session():
    try:
        session_id = request.args.get("session_id")
        user_id    = request.args.get("user_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            return jsonify({"success": False, "message": "Payment not completed"}), 200

        meta = session.metadata.to_dict() if session.metadata else {}
        plan_key = meta.get("plan")
        currency = meta.get("currency", "usd")
        amount   = PLANS[plan_key][currency] if plan_key in PLANS else 0
        sub_user_id = meta.get("user_id") or user_id

        db = get_db()
        expires = _activate_subscription(db, sub_user_id, plan_key, currency, amount, session_id=session_id)

        return jsonify({"success": True, "plan": plan_key, "expires_at": expires.isoformat()}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
