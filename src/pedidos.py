import json
import uuid
import os
import boto3
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
tabla_pedidos = dynamodb.Table(os.environ.get('TABLA_PEDIDOS'))
ESTADOS_VALIDOS = os.environ.get('ESTADOS_PERMITIDOS', '').split(',')
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Credentials": True,
}

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

def obtener_identidad(event):
    """Extrae los roles y el ID de usuario desde el JWT inyectado por API Gateway"""
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    roles = claims.get("roles", [])
    user_id = claims.get("sub", "id_desconocido")
    if not roles:
        headers = event.get("headers", {})
        roles = [headers.get("x-simular-rol", "")]
        user_id = headers.get("x-simular-usuario", "anonimo")
    return roles, user_id



def crear_pedido(event, context):
    roles, user_id = obtener_identidad(event)
    
    if "Cliente" not in roles and "Operador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
            }

    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    
    if not body.get("items"):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Faltan los items del pedido"}),
            "headers": CORS_HEADERS
            }
    
    cliente_id = user_id if "Cliente" in roles else body.get("cliente_id", user_id)
    
    nuevo_pedido = {
        "id": str(uuid.uuid4()),
        "cliente_id": cliente_id,
        "items": body.get("items"),
        "estado": "CREADO",
        "fecha_creacion": datetime.now().isoformat()
    }
    
    tabla_pedidos.put_item(Item=nuevo_pedido)
    return {
        "statusCode": 201,
        "body": json.dumps(nuevo_pedido, cls=DecimalEncoder),
        "headers": CORS_HEADERS
        }

def obtener_pedido(event, context):
    roles, user_id = obtener_identidad(event)
    path_params = event.get("pathParameters", {}) or {}
    pedido_id = path_params.get("id")
    
    respuesta = tabla_pedidos.get_item(Key={"id": pedido_id})
    pedido = respuesta.get("Item")
    
    if not pedido:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Pedido no encontrado"}),
            "headers": CORS_HEADERS
            }
        
    if "Cliente" in roles and "Admin" not in roles and "Operador" not in roles:
        if pedido.get("cliente_id") != user_id:
            return {
                "statusCode": 403,
                "body": json.dumps({"error": "Acceso denegado"}),
                "headers": CORS_HEADERS
                }
            
    return {
        "statusCode": 200,
        "body": json.dumps(pedido,cls=DecimalEncoder),
        "headers": CORS_HEADERS
        }


def actualizar_estado(event, context):
    roles, user_id = obtener_identidad(event)
    
    if "Operador" not in roles and "Admin" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
            }
        
    path_params = event.get("pathParameters", {}) or {}
    pedido_id = path_params.get("id")
    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    nuevo_estado = body.get("estado")
    
    if nuevo_estado not in ESTADOS_VALIDOS:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Estado inválido"}),
            "headers": CORS_HEADERS
            }
        
    respuesta = tabla_pedidos.get_item(Key={"id": pedido_id})
    pedido = respuesta.get("Item")
    
    if not pedido:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Pedido no encontrado"}),
            "headers": CORS_HEADERS
            }
        
    estado_actual = pedido.get("estado")
    
    if nuevo_estado == "DESPACHADO" and estado_actual not in ["ACEPTADO"]:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "El pedido no puede ser despachado sin ser aceptado previamente."}),
            "headers": CORS_HEADERS
            }
    
    tabla_pedidos.update_item(
        Key={"id": pedido_id},
        UpdateExpression="SET estado = :nuevo_estado",
        ExpressionAttributeValues={":nuevo_estado": nuevo_estado}
    )
    
    pedido["estado"] = nuevo_estado
    return {
        "statusCode": 200,
        "body": json.dumps(pedido,cls=DecimalEncoder),
        "headers": CORS_HEADERS
        }