import json
from contextlib import asynccontextmanager
from typing import Mapping, Any, Optional

from aio_pika import Message
from aio_pika.abc import AbstractRobustExchange, AbstractRobustConnection, AbstractRobustChannel
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import pymongo
import aio_pika
import uuid

from pymongo import MongoClient
from pymongo.database import Database

templates: Optional[Jinja2Templates] = None
client: Optional[MongoClient[Mapping[str, Any]]] = None
db: Optional[Database[Mapping[str, Any]]] = None
connection: Optional[AbstractRobustConnection] = None
channel: Optional[AbstractRobustChannel] = None
exchange: Optional[AbstractRobustExchange] = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global templates, client, db, connection, channel, exchange
    templates = Jinja2Templates(directory="templates")
    client = pymongo.MongoClient("localhost", 27017)
    db = client["electrical_bills"]

    connection = await aio_pika.connect_robust(
        "amqp://guest:guest@localhost/",
    )
    channel = await connection.channel()

    exchange = await channel.declare_exchange(name="electrical_bills", type="direct")

    yield


app = FastAPI(lifespan=lifespan)


async def send_request_and_get_response(data: dict) -> dict:
    temp_queue_routing_key = str(uuid.uuid4())

    queue = await channel.declare_queue(name=f"temp-{temp_queue_routing_key}", auto_delete=True)
    await queue.bind(exchange=exchange, routing_key=temp_queue_routing_key)

    await exchange.publish(
        Message(
            json.dumps({"routing_key": temp_queue_routing_key, "data": data}).encode(),
        ),
        routing_key="electrical.bills.updates"
    )

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                response: dict = json.loads(message.body.decode())
                return response


def mongo_general_data_get(_id: str):
    result = db["general_data"].find_one({"_id": _id})
    if not result:
        return result

    return result.get("data")


# Індексна сторінка
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "meters_data": db["meters_data"].find(
        sort=[("date_time", pymongo.DESCENDING)]), "response": None})


# Обробник для додавання показань лічильника
@app.post("/add_reading", response_class=HTMLResponse)
async def add_reading(
        request: Request,
        meter_id: int = Form(...),
        phase1: float = Form(...),  # День
        phase2: float = Form(...)  # Ніч
):
    response = None

    # Перевірка на негативні значення
    if meter_id < 0:
        response = "Індекс не може бути меншим за нуль"
    elif phase1 < 0:
        response = "Денні показання не можуть бути меншими за нуль"
    elif phase2 < 0:
        response = "Нічні показання не можуть бути меншими за нуль"

    if not response:
        response = (await send_request_and_get_response(
            {"meter_id": meter_id, "day": phase1, "night": phase2})
                    ).get("response")

    return templates.TemplateResponse("index.html", {"request": request, "meters_data": db["meters_data"].find(
        sort=[("date_time", pymongo.DESCENDING)]), "response": response})


# Обробник для додавання лічильника
@app.post("/add_meter", response_class=HTMLResponse)
async def add_meter(
        request: Request,
        meter_id: int = Form(...)
):
    response = None

    # Перевірка на негативні значення
    if meter_id < 0:
        response = "Ідентифікатор лічильника не може бути меншим за нуль"

    if not response:
        response = (await send_request_and_get_response({"meter_id": meter_id})).get("response")

    return templates.TemplateResponse("meters.html",
                                      {"request": request, "meters": db["meters"].find(), "response": response})


# Обробник для додавання тарифу
@app.post("/add_tariff", response_class=HTMLResponse)
async def add_tariff(
        request: Request,
        day_tariff: float = Form(...),
        night_tariff: float = Form(...),
        set_as_current: bool = Form(...)
):
    response = None

    # Перевірка на негативні значення
    if day_tariff < 0:
        response = "Денний тариф не може бути меншим за нуль"
    elif night_tariff < 0:
        response = "Нічний тариф не може бути меншим за нуль"

    if not response:
        response = (await send_request_and_get_response(
            {"day_tariff": day_tariff, "night_tariff": night_tariff, "set_as_current": set_as_current})
                    ).get("response")

    return templates.TemplateResponse("tariffs.html", {"request": request,
                                                       "tariff_history": db['tariff_history'].find(
                                                           sort=[("date_time", pymongo.DESCENDING)]),
                                                       "current_tariff": mongo_general_data_get("current_tariff"),
                                                       "response": response})


# Обробник для встановлення тарифу
@app.post("/set_tariff", response_class=HTMLResponse)
async def set_tariff(
        request: Request,
        tariff_id: str = Form(...)  # tariff_id приходить як строка
):
    response = (await send_request_and_get_response({"tariff_id": tariff_id})).get("response")

    # Тут немає числової валідації, просто повертаємо сторінку
    return templates.TemplateResponse("tariffs.html", {"request": request,
                                                       "tariff_history": db['tariff_history'].find(
                                                           sort=[("date_time", pymongo.DESCENDING)]),
                                                       "current_tariff": mongo_general_data_get("current_tariff"),
                                                       "response": response})


# GET-запити для інших сторінок
@app.get("/meters", response_class=HTMLResponse)
async def get_meters(request: Request):
    return templates.TemplateResponse("meters.html",
                                      {"request": request, "meters": db["meters"].find(), "response": None})


@app.get("/tariffs", response_class=HTMLResponse)
async def get_tariffs(request: Request):
    return templates.TemplateResponse("tariffs.html", {"request": request,
                                                       "tariff_history": db['tariff_history'].find(
                                                           sort=[("date_time", pymongo.DESCENDING)]),
                                                       "current_tariff": mongo_general_data_get("current_tariff"),
                                                       "response": None})
