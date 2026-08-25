from backend.gee_engine import _ee_ready
import config
config.initialize_gee()
print("After initialize_gee(): _ee_ready() =", _ee_ready())
