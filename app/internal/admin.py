from fastapi import HTTPException

def get_admin_info():
    return {"admin": "admin_user"}

def verify_admin(username: str):
    if username != "admin_user":
        raise HTTPException(status_code=403, detail="Not an admin")