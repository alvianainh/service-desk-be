from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from main_router import router as auth_router
# from quis_router import router as quiz_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/")
async def root():
    logger.info("GET / - Root endpoint accessed")
    return {"message": "Server is running!"}


# Include routers
app.include_router(auth_router)
# app.include_router(quiz_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=9000, reload=False)

