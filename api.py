from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from pipeline import router as pipeline_router
from tickets import routes as ticket_routes
from tickets import routes_bidang as ticket_routes_bidang
from tickets import routes_seksi as ticket_routes_seksi
from tickets import routes_pengguna as ticket_routes_pengguna
from tickets import routes_admin_opd as ticket_routes_admin_opd
from tickets import routes_teknisi as ticket_routes_teknisi
from tickets import routes_admin_kota as ticket_routes_admin_kota
from tickets import routes_seksi as ticket_routes_seksi
from websocket.router import router as websocket_router
from opd import routes as opd_routes
from roles import routes as roles_routes
from articles import routes as articles_routes
from chat import routes as chat_routes

# from fastapi.openapi.models import APIKey, APIKeyIn, SecuritySchemeType


app = FastAPI(
    title="Service Desk API",
    swagger_ui_init_oauth={},
    openapi_tags=[
        {"name": "auth", "description": "Authentication & SSO"},
    ],
    components={
        "securitySchemes": {
            "SSOBearer": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT"
            }
        }
    },
    security=[{"SSOBearer": []}]
)

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


app.include_router(pipeline_router, tags=["auth"])
app.include_router(roles_routes.router, tags=["roles"])
app.include_router(opd_routes.router)
app.include_router(roles_routes.router, tags=["roles"])
app.include_router(ticket_routes.router, prefix="/api", tags=["tickets"])
app.include_router(ticket_routes_seksi.router, prefix='/api', tags=["seksi"])
app.include_router(ticket_routes_teknisi.router, prefix="/api", tags=["teknisi"])
app.include_router(ticket_routes_bidang.router, prefix="/api", tags=["bidang"])
app.include_router(ticket_routes_pengguna.router, prefix="/api", tags=["riwayat pengguna"])
app.include_router(ticket_routes_admin_opd.router, prefix="/api", tags=["admin opd dashboard"])
app.include_router(ticket_routes_admin_kota.router, prefix="/api", tags=["admin kota dashboard"])
app.include_router(websocket_router)
app.include_router(articles_routes.router, tags=["articles"])
app.include_router(chat_routes.router, tags=["chat"])



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=9000, reload=False)