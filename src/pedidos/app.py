from litestar import Litestar, get, post
from mangum import Mangum

@post("/pedidos")
async def crear_pedido(data: dict) -> dict:
    return {"status": "Creado", "id_pedido": "12345", "payload": data}

@get("/pedidos/{pedido_id:str}")
async def obtener_pedido(pedido_id: str) -> dict:
    return {"id_pedido": pedido_id, "status": "En_Preparacion"}

app = Litestar(route_handlers=[crear_pedido, obtener_pedido])
handler = Mangum(app)