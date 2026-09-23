import json
import uuid
import os
import boto3

dynamodb = boto3.resource('dynamodb')
tabla_catalogo = dynamodb.Table(os.environ.get('TABLA_CATALOGO'))

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

def crear_producto(event, context):
    roles = obtener_identidad(event)
    
    if "Admin" not in roles and "Operador" not in roles:
        return {"statusCode": 403, "body": json.dumps({"error": "Acceso denegado"})}

    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    
    if not body.get("nombre") or not body.get("precio"):
        return {"statusCode": 400, "body": json.dumps({"error": "Faltan datos requeridos (nombre, precio)"})}
        
    producto = {
        "id": str(uuid.uuid4()),
        "nombre": body.get("nombre"),
        "precio": body.get("precio"),
        "stock": body.get("stock", 0) 
    }
    
    tabla_catalogo.put_item(Item=producto)
    return {"statusCode": 201, "body": json.dumps(producto)}


def listar_productos(event, context):

    respuesta = tabla_catalogo.scan()
    productos = respuesta.get("Items", [])
    
    return {"statusCode": 200, "body": json.dumps(productos)}

def actualizar_stock(event, context):
    roles = obtener_identidad(event)
    if "Admin" not in roles and "Operador" not in roles:
        return {"statusCode": 403, "body": json.dumps({"error": "Acceso denegado"})}

    path_params = event.get("pathParameters", {}) or {}
    producto_id = path_params.get("id")
    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    
    variacion_stock = body.get("cantidad") 
    
    if not variacion_stock or not isinstance(variacion_stock, int):
        return {"statusCode": 400, "body": json.dumps({"error": "Debe enviar una 'cantidad' entera."})}

    try:
        respuesta = tabla_catalogo.update_item(
            Key={"id": producto_id},
            UpdateExpression="ADD stock :val",
            ExpressionAttributeValues={":val": variacion_stock},
            ReturnValues="UPDATED_NEW"
        )
        nuevo_stock = int(respuesta["Attributes"]["stock"])
        
        if nuevo_stock < 0:
            tabla_catalogo.update_item(
                Key={"id": producto_id},
                UpdateExpression="ADD stock :val",
                ExpressionAttributeValues={":val": abs(variacion_stock)}
            )
            return {"statusCode": 400, "body": json.dumps({"error": "Stock insuficiente"})}

        return {"statusCode": 200, "body": json.dumps({"id": producto_id, "nuevo_stock": nuevo_stock})}
        
    except Exception as e:
         return {"statusCode": 500, "body": json.dumps({"error": "Error al actualizar stock"})}
