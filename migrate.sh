#!/bin/sh
alembic revision --autogenerate -m "ValorsBot model"
alembic upgrade head
