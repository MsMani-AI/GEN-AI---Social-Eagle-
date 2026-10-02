from fastapi import FastAPI

app = FastAPI(title="My Basic FastAPI App")


@app.get("/")
def welcome():
    return {"message": "Hello, FastAPI"}


@app.get("/greet/{name}")
def greet(name: str):
    return {
        "name": name,
        "message": f"Hello, {name}!"
    }