from app.models.team import Department, User
from tests.conftest import auth_headers


def test_member_list_includes_department_name(client, db, super_admin):
    department = Department(name="运营组")
    db.add(department)
    db.flush()
    db.add(User(username="team-member", password_hash="hash", department_id=department.id, is_active=True))
    db.commit()
    response = client.get("/api/team/member", headers=auth_headers(super_admin))
    assert response.status_code == 200
    member = next(item for item in response.json()["items"] if item["username"] == "team-member")
    assert member["department_id"] == department.id
    assert member["department_name"] == "运营组"
    admin = next(item for item in response.json()["items"] if item["username"] == super_admin.username)
    assert admin["department_name"] is None
    filtered = client.get("/api/team/member", params={"dept_id": department.id}, headers=auth_headers(super_admin))
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["department_name"] == "运营组"
