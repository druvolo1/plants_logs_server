# main.py - FastAPI application
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from database import get_db, engine
import models
import schemas
import crud
import auth
from dotenv import load_dotenv
import os

load_dotenv()
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")  # Create static/ if needed for CSS
templates = Jinja2Templates(directory="templates")  # Create templates/ for HTML

models.Base.metadata.create_all(bind=engine)  # Create DB tables

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY"))

# Setup initial admin if not exists (run once or in migration)
@app.on_event("startup")
def create_admin():
    db = next(get_db())
    admin_email = os.getenv("ADMIN_USERNAME")
    admin_pass = os.getenv("ADMIN_PASSWORD")
    if not crud.get_user_by_email(db, admin_email):
        crud.create_user(db, schemas.UserCreate(email=admin_email, password=admin_pass), is_admin=True)

# Google OAuth login
@app.get("/login/google")
async def login_google(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    return await auth.oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    token = await auth.oauth.google.authorize_access_token(request)
    user_info = await auth.oauth.google.parse_id_token(request, token)
    email = user_info["email"]
    user = crud.get_user_by_email(db, email)
    if not user:
        user = crud.create_user(db, schemas.UserCreate(email=email))
    access_token = crud.create_access_token(data={"sub": user.email})
    response = RedirectResponse(url="/users")  # Or your users page
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response

# Admin login (local password)
@app.post("/login/admin", response_model=schemas.Token)
def login_admin(form_data: schemas.UserLogin = Depends(schemas.UserLogin), db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, form_data.username, form_data.password)
    if not user or not user.is_admin:
        raise HTTPException(status_code=401, detail="Invalid credentials or not admin")
    access_token = crud.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# Users page (example HTML, protected)
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db), current_user: schemas.User = Depends(auth.get_current_user)):
    users = crud.get_users(db)
    return templates.TemplateResponse("users.html", {"request": request, "users": users})

# Admin manage users
@app.get("/admin/users", response_model=list[schemas.User])
def list_users(db: Session = Depends(get_db), current_admin: schemas.User = Depends(auth.get_current_admin)):
    return crud.get_users(db)

@app.post("/admin/users", response_model=schemas.User)
def create_user_admin(user: schemas.UserCreate, db: Session = Depends(get_db), current_admin: schemas.User = Depends(auth.get_current_admin)):
    return crud.create_user(db, user)

@app.delete("/admin/users/{user_id}")
def delete_user_admin(user_id: int, db: Session = Depends(get_db), current_admin: schemas.User = Depends(auth.get_current_admin)):
    if crud.delete_user(db, user_id):
        return {"status": "success"}
    raise HTTPException(404, "User not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)