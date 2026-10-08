from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Hola, FastAPI!"}


@app.get("/saludo/{nombre}")
def saludar(nombre: str):
    return {"message": f"Hola, {nombre}!"}
