from paho.mqtt import client as mqtt_client
import random
import logging

broker = '31.171.241.69'
port = 1883
# generate client ID with pub prefix randomly
client_id = f'backend-{random.randint(0, 100)}'
# username = 'emqx'
# password = 'public'

def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT Broker!")
        else:
            logging.info("Failed to connect, return code %d\n", rc)

    client = mqtt_client.Client(client_id)
    #client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client

def subscribe(client, topic):
    def on_message(client, userdata, msg):
        if(msg.payload.decode() == "READY"):
            logging.info("THE CLUSTER IS READY!!!")
        #print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
    client.subscribe(topic)
    client.on_message = on_message


def publish(client, topic, msg):
    client.publish(topic, msg)