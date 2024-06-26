# library imports
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


# module imports
from .routes import blog_content,users, auth, password_reset,NonTelescopicPipe

# initialize an app
app = FastAPI()

# Handle CORS protection
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Construct the absolute path for the static directory# Construct the absolute path for the static directory
current_file_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.abspath(os.path.join(current_file_dir, "..","static"))

# Ensure the static directory exists
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

# Mount the static directory for serving images
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# register all the router endpoint
app.include_router(blog_content.router)
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(password_reset.router)
app.include_router(NonTelescopicPipe.router)


@app.get("/")
def get():
    return {"msg": "Hello world"}