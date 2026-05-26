import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
"""
Full End-to-End Pipeline Test
Simulates what happens when a user uploads a file from the frontend
"""
import os, json, tempfile, zipfile
sys.path.insert(0, os.path.dirname(__file__))
from predictor import BugPredictor

print("=" * 65)
print("  FULL PIPELINE TEST — Source Code → Bug Report")
print("=" * 65)

predictor = BugPredictor()

# ─── Test 1: Analyze a Java file directly ────────────────────────────────────
print("\n" + "─"*65)
print("TEST 1: Java file with high coupling (Crash bug expected)")
print("─"*65)

java_code = '''
import java.util.List;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import com.example.repo.UserRepository;
import com.example.repo.OrderRepository;
import com.example.service.EmailService;
import com.example.service.PaymentService;
import com.example.util.CacheManager;

@Service
public class OrderProcessingService extends BaseService implements IOrderService {
    @Autowired private UserRepository userRepo;
    @Autowired private OrderRepository orderRepo;
    @Autowired private EmailService emailSvc;
    @Autowired private PaymentService paymentSvc;
    @Autowired private CacheManager cache;
    private int maxRetries;
    private String apiKey;
    private Map<String, Object> config;

    public Order createOrder(Long userId, List<Item> items) {
        User user = userRepo.findById(userId).orElse(null);
        if (user == null) throw new RuntimeException("User not found");
        for (Item item : items) {
            if (item.getStock() <= 0) throw new IllegalArgumentException("Out of stock");
            if (item.getPrice() < 0) continue;
        }
        Order order = new Order(user, items);
        orderRepo.save(order);
        emailSvc.sendConfirmation(user.getEmail(), order.getId());
        return order;
    }

    public boolean processPayment(Long orderId, PaymentInfo info) {
        Order order = orderRepo.findById(orderId).orElse(null);
        if (order == null) return false;
        try {
            boolean paid = paymentSvc.charge(info.getCard(), order.getTotal());
            if (paid) {
                order.setStatus("PAID");
                orderRepo.save(order);
                cache.invalidate("orders:" + orderId);
                emailSvc.sendReceipt(order.getUser().getEmail());
            }
            return paid;
        } catch (PaymentException e) {
            orderRepo.updateStatus(orderId, "FAILED");
            return false;
        }
    }

    public List<Order> getHistory(Long userId, String status, int page) {
        if (userId == null) return new ArrayList<>();
        List<Order> orders = orderRepo.findByUserAndStatus(userId, status, page);
        for (Order o : orders) {
            if (o.getItems() != null && !o.getItems().isEmpty()) {
                o.setTotal(o.getItems().stream().mapToDouble(Item::getPrice).sum());
            }
        }
        return orders;
    }

    public void cancelOrder(Long orderId) {
        Order order = orderRepo.findById(orderId).orElse(null);
        if (order != null && "PENDING".equals(order.getStatus())) {
            order.setStatus("CANCELLED");
            orderRepo.save(order);
            emailSvc.sendCancellation(order.getUser().getEmail());
            paymentSvc.refund(order.getPaymentId());
        }
    }
}
'''

# Write to temp file
tmp = tempfile.NamedTemporaryFile(suffix='.java', delete=False, mode='w', encoding='utf-8')
tmp.write(java_code)
tmp.close()

bugs = predictor.analyze_file(tmp.name)
os.unlink(tmp.name)

if bugs:
    for b in bugs:
        print(f"  Bug ID       : {b['bug_id']}")
        print(f"  Type         : {b['type']}")
        print(f"  Severity     : {b['severity']}")
        print(f"  Line Number  : {b['line_number']}")
        print(f"  Confidence   : {b['defect_probability']*100:.1f}%")
        print(f"  Assigned To  : {b['assigned_to']}")
        print(f"  AI Reason    : {b['ai_reason']}")
        print(f"  Fix          : {b['suggested_fix']}")
else:
    print("  No bugs detected")

# ─── Test 2: Python file ──────────────────────────────────────────────────────
print("\n" + "─"*65)
print("TEST 2: Python file")
print("─"*65)

py_code = '''
import os, re, json, csv, requests, pandas, numpy, sklearn, torch

class DataPipeline:
    def __init__(self):
        self.cache = {}
        self.buffer = []
        self.errors = []
        self.retries = 0
        self.config = {}
        self.logger = None

    def load(self, path):
        if path is None: return False
        with open(path) as f:
            for line in f:
                if line.strip():
                    self.buffer.append(json.loads(line))
        return True

    def transform(self, data):
        result = []
        for item in data:
            if item.get("type") == "A":
                val = item["value"] * 2
                if val > 100:
                    result.append({"id": item["id"], "val": val, "flag": True})
                elif val > 50:
                    result.append({"id": item["id"], "val": val, "flag": False})
                else:
                    continue
            elif item.get("type") == "B":
                for sub in item.get("children", []):
                    result.append(self._process_sub(sub))
        return result

    def _process_sub(self, sub):
        try:
            return {"id": sub["id"], "val": sub["value"] / sub["count"]}
        except ZeroDivisionError:
            return {"id": sub["id"], "val": 0}

    def validate(self, records):
        for r in records:
            if not isinstance(r.get("id"), int): self.errors.append(r)
            if r.get("val") < 0: self.errors.append(r)
        return len(self.errors) == 0

    def export(self, records, path):
        with open(path, "w") as f:
            json.dump(records, f, indent=2)
'''

tmp2 = tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w', encoding='utf-8')
tmp2.write(py_code)
tmp2.close()

bugs2 = predictor.analyze_file(tmp2.name)
os.unlink(tmp2.name)

if bugs2:
    for b in bugs2:
        print(f"  Bug ID    : {b['bug_id']}")
        print(f"  Type      : {b['type']}")
        print(f"  Severity  : {b['severity']}")
        print(f"  Reason    : {b['ai_reason']}")
        print(f"  Fix       : {b['suggested_fix']}")
else:
    print("  No bugs detected")

# ─── Test 3: Log file ─────────────────────────────────────────────────────────
print("\n" + "─"*65)
print("TEST 3: Error log file")
print("─"*65)

log_content = """
2026-05-21 09:10:01 INFO  Application started successfully
2026-05-21 09:12:45 ERROR NullPointerException at com.example.OrderService.findById(OrderService.java:89)
2026-05-21 09:13:01 FATAL StackOverflowError at com.example.TreeParser.parse(TreeParser.java:34)
2026-05-21 09:15:22 ERROR ArithmeticException: / by zero at com.example.Calculator.divide(Calculator.java:56)
2026-05-21 09:16:00 WARN  IllegalArgumentException: invalid input at com.example.Validator.check
2026-05-21 09:20:00 INFO  Request processed in 230ms
2026-05-21 09:22:11 ERROR ArrayIndexOutOfBoundsException at com.example.ArrayUtil.get(ArrayUtil.java:12)
"""

tmp3 = tempfile.NamedTemporaryFile(suffix='.log', delete=False, mode='w', encoding='utf-8')
tmp3.write(log_content)
tmp3.close()

bugs3 = predictor.analyze_file(tmp3.name)
os.unlink(tmp3.name)

print(f"  Bugs found in log: {len(bugs3)}")
for b in bugs3:
    print(f"    {b['bug_id']} | {b['type']:12s} | {b['severity']:8s} | Line {b['line_number']} | {b['description']}")

# ─── Test 4: ZIP file with multiple source files ──────────────────────────────
print("\n" + "─"*65)
print("TEST 4: ZIP file (multiple files inside)")
print("─"*65)

zip_tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
zip_tmp.close()

with zipfile.ZipFile(zip_tmp.name, 'w') as zf:
    zf.writestr('AuthService.java', java_code)
    zf.writestr('pipeline.py', py_code)
    zf.writestr('errors.log', log_content)

zip_bugs = predictor.analyze_zip(zip_tmp.name)
os.unlink(zip_tmp.name)

print(f"  Total bugs from ZIP: {len(zip_bugs)}")
for b in zip_bugs:
    print(f"    {b['bug_id']} | {b['file']:25s} | {b['type']:12s} | {b['severity']}")

# ─── Final summary ────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
all_bugs = bugs + bugs2 + bugs3 + zip_bugs
print(f"  TOTAL BUGS DETECTED (all tests): {len(all_bugs)}")
print("\n  Sample JSON output for API response:")
if bugs:
    print(json.dumps(bugs[0], indent=4))
print("=" * 65)
print("  FULL PIPELINE TEST COMPLETE")
print("=" * 65)
