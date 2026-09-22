from litestar import Litestar, post, patch
from mangum import Mangum

@post("/encargos")
async def solicitar_encargo(data: dict) -> dict:
    return {"status": "Solicitado", "id_encargo": "9876", "requerimientos": data}

@patch("/encargos/{encargo_id:str}/cotizar")
async def cotizar_encargo(encargo_id: str, cotizacion: dict) -> dict:
    return {"id_encargo": encargo_id, "status": "Cotizado", "precio": cotizacion.get("precio")}

app = Litestar(route_handlers=[solicitar_encargo, cotizar_encargo])
handler = Mangum(app)