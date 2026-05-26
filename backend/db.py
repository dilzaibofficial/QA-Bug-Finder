from pymongo import MongoClient
import config

_client = None
_db     = None

def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(config.MONGO_URI)
        _db     = _client[config.DB_NAME]
        # Indexes for fast queries
        _db.users.create_index("email", unique=True)
        _db.bugs.create_index("analysis_id")
        _db.history.create_index([("user_id", 1), ("analyzed_on", -1)])
        _db.analysis.create_index([("user_id", 1), ("start_time", -1)])
    return _db
