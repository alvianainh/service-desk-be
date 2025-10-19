from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from pipeline import router as auth_router
from tickets import routes as ticket_routes
from opd import routes as opd_routes
from roles import routes as roles_routes
from articles import routes as articles_routes

app = FastAPI(
    title="Service Desk API")

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


app.include_router(auth_router)
app.include_router(roles_routes.router, tags=["Roles"])
app.include_router(opd_routes.router)
app.include_router(roles_routes.router, tags=["Roles"])
app.include_router(ticket_routes.router, prefix="/api", tags=["Tickets"])
app.include_router(articles_routes.router, tags=["Articles"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=9000, reload=False)

