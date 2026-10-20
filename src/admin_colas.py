import json
import boto3
from src.utils import CORS_HEADERS, obtener_identidad

sqs = boto3.client('sqs')

def crear_cola(event, context):
    roles, _ = obtener_identidad(event)
    
    if "Administrador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado. Solo administradores."}),
            "headers": CORS_HEADERS
        }

    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    nombre_cola = body.get("nombre")

    if not nombre_cola:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Falta el parámetro 'nombre' para crear la cola."}),
            "headers": CORS_HEADERS
        }

    try:
        respuesta = sqs.create_queue(QueueName=nombre_cola)
        return {
            "statusCode": 201,
            "body": json.dumps({
                "mensaje": f"Cola '{nombre_cola}' creada exitosamente",
                "url": respuesta['QueueUrl']
            }),
            "headers": CORS_HEADERS
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Error al crear la cola: {str(e)}"}),
            "headers": CORS_HEADERS
        }

def eliminar_cola(event, context):
    roles, _ = obtener_identidad(event)
    
    if "Administrador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado."}),
            "headers": CORS_HEADERS
        }


    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    url_cola = body.get("url")

    if not url_cola:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Falta el parámetro 'url' de la cola a eliminar."}),
            "headers": CORS_HEADERS
        }

    try:
        sqs.delete_queue(QueueUrl=url_cola)
        return {
            "statusCode": 200,
            "body": json.dumps({"mensaje": f"Cola en {url_cola} eliminada."}),
            "headers": CORS_HEADERS
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Error al eliminar la cola: {str(e)}"}),
            "headers": CORS_HEADERS
        }