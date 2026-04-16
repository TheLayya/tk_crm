import sys
sys.path.insert(0, '/home/thelayya/.openclaw/tiktok-monitor/backend')
import os
os.chdir('/home/thelayya/.openclaw/tiktok-monitor/backend')

try:
    from app.models.proxy_node import ProxyNode
    print("✓ models.proxy_node OK")
except Exception as e:
    print(f"✗ models.proxy_node FAILED: {e}")

try:
    from app.schemas.proxy_node import ProxyNodeCreate, ProxyNodeResponse, ProxyNodeStats
    print("✓ schemas.proxy_node OK")
except Exception as e:
    print(f"✗ schemas.proxy_node FAILED: {e}")

try:
    from app.services.proxy_node_service import get_nodes, create_node, get_stats
    print("✓ services.proxy_node_service OK")
except Exception as e:
    print(f"✗ services.proxy_node_service FAILED: {e}")

try:
    from app.services.proxy_node_import_service import import_from_csv, generate_template_csv
    print("✓ services.proxy_node_import_service OK")
except Exception as e:
    print(f"✗ services.proxy_node_import_service FAILED: {e}")

try:
    from app.services.proxy_node_export_service import export_to_csv, export_to_excel
    print("✓ services.proxy_node_export_service OK")
except Exception as e:
    print(f"✗ services.proxy_node_export_service FAILED: {e}")

try:
    from app.services.proxy_node_test_service import test_node, batch_test_nodes
    print("✓ services.proxy_node_test_service OK")
except Exception as e:
    print(f"✗ services.proxy_node_test_service FAILED: {e}")

try:
    from app.api.proxy_nodes import router
    print(f"✓ api.proxy_nodes OK ({len(router.routes)} routes)")
except Exception as e:
    print(f"✗ api.proxy_nodes FAILED: {e}")

print("\nAll checks done.")
