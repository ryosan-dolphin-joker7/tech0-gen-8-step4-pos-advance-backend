from fastapi import FastAPI

# FastAPIのアプリを作成
app = FastAPI()

# ルートエンドポイントを定義
@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}

# パスパラメータを受け取るエンドポイント
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}
