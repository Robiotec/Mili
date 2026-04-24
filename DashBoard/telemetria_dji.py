import json
import os
import paho.mqtt.client as mqtt

broker = os.getenv("DJI_MQTT_BROKER", "192.168.1.92")
port = int(os.getenv("DJI_MQTT_PORT", "1883"))

def on_connect(client, userdata, flags, reason_code, properties=None):
    print("Conectado:", reason_code)

    # Topics típicos de DJI Cloud API
    client.subscribe("thing/product/+/osd")
    client.subscribe("thing/product/+/state")
    client.subscribe("thing/product/+/events")
    client.subscribe("thing/product/+/services_reply")

def on_message(client, userdata, msg):
    print(f"\nTopic: {msg.topic}")
    payload = msg.payload.decode(errors="ignore")
    print("Mensaje:", payload)

    try:
        data = json.loads(payload)
        print("JSON parseado:", data)
    except Exception:
        pass

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(broker, port)
client.loop_forever()