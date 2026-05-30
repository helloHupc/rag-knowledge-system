from __future__ import annotations


def test_system_config_crud_flow(client):
    create_response = client.post(
        "/api/v1/admin/system-configs",
        json={
            "config_key": "ui.theme",
            "config_value": {"mode": "light"},
            "description": "theme config",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    config_id = created["id"]

    detail_response = client.get(f"/api/v1/admin/system-configs/{config_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["config_key"] == "ui.theme"

    update_response = client.patch(
        f"/api/v1/admin/system-configs/{config_id}",
        json={
            "config_value": {"mode": "dark"},
            "description": "updated theme config",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["config_value"] == {"mode": "dark"}

    list_response = client.get("/api/v1/admin/system-configs")
    assert list_response.status_code == 200
    assert list_response.json()["data"]["total"] >= 1




def test_identity_admin_crud_flow(client):
    dept_response = client.post(
        "/api/v1/admin/departments",
        json={
            "dept_code": "hr",
            "dept_name": "Human Resources",
            "external_source": "mock-hris",
            "external_id": "dept-001",
        },
    )
    assert dept_response.status_code == 200
    assert dept_response.json()["data"]["dept_code"] == "hr"

    role_response = client.post(
        "/api/v1/admin/roles",
        json={
            "role_code": "hr_admin",
            "role_name": "HR Admin",
        },
    )
    assert role_response.status_code == 200
    assert role_response.json()["data"]["role_code"] == "hr_admin"

    user_response = client.post(
        "/api/v1/admin/users",
        json={
            "user_id": "u1001",
            "display_name": "Alice",
            "email": "alice@example.com",
            "employee_no": "E1001",
            "department_codes": ["hr"],
            "role_codes": ["hr_admin"],
            "primary_dept_code": "hr",
            "external_source": "mock-hris",
            "external_id": "employee-1001",
        },
    )
    assert user_response.status_code == 200
    user = user_response.json()["data"]
    assert user["department_codes"] == ["hr"]
    assert user["role_codes"] == ["hr_admin"]
    assert user["external_source"] == "mock-hris"

    detail_response = client.get("/api/v1/admin/users/u1001")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["display_name"] == "Alice"

    update_response = client.patch(
        "/api/v1/admin/users/u1001",
        json={
            "display_name": "Alice Zhang",
            "role_codes": [],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["display_name"] == "Alice Zhang"
    assert updated["department_codes"] == ["hr"]
    assert updated["role_codes"] == []

    users_response = client.get("/api/v1/admin/users?keyword=Alice")
    assert users_response.status_code == 200
    assert users_response.json()["data"]["total"] == 1
