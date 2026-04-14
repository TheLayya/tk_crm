import sys
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from app.models.team import User, UserRole

db = SessionLocal()

# 清理孤立的 user_roles 记录（user_id 不存在于 users 表的）
user_ids = {u.id for u in db.query(User).all()}
orphan_roles = db.query(UserRole).filter(~UserRole.user_id.in_(user_ids)).all()
print(f'发现孤立 user_roles 记录: {len(orphan_roles)} 条')
for r in orphan_roles:
    db.delete(r)
db.commit()
print('清理完成')

# 显示当前用户列表
users = db.query(User).all()
for u in users:
    print(f'  id={u.id} username={u.username} is_active={u.is_active}')

db.close()
