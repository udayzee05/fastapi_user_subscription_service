# library imports
import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# module imports
from api.routes import users, auth, password_reset, NonTelescopicPipe, telescopic, mildSteelBars, dataManipulation, userProfile, testserv,workorder
from api.routes.subscription import plan, webhook, subscribe, invoice

# initialize an app
app = FastAPI(title="Alluvium AI Services Platform", version="1.0.0")

# Handle CORS protection
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Construct the path for the static directory
current_file_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_file_dir, "static")  # This points to the "static" directory in the project root

# Mount the static directory for serving images
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Register all the router endpoints
app.include_router(users.router)
app.include_router(userProfile.router)
app.include_router(auth.router)
app.include_router(password_reset.router)
app.include_router(NonTelescopicPipe.router)
app.include_router(telescopic.router)
app.include_router(mildSteelBars.router)
app.include_router(testserv.router)
app.include_router(workorder.router)

app.include_router(dataManipulation.router)
app.include_router(plan.router)
app.include_router(webhook.router)
app.include_router(subscribe.router)
app.include_router(invoice.router)

# Default route
@app.get("/")
def get():
    return {"msg": "Welcome to Alluvium AI Services Platform"}

# Run the application
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
