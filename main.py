from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column,Integer, String, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime,date,timezone
from dotenv import load_dotenv
import os
import logging
from typing import Optional
from pydantic import BaseModel
from typing import List
import uuid

# ログの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
load_dotenv()  # .env をデフォルトとして読み込む
load_dotenv(dotenv_path=".env.local", override=True)  # .env.local があれば上書き

# 環境変数の読み込み
DB_HOST = os.getenv("DB_HOST") 
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SSL_CA = os.getenv("DB_SSL_CA")

# MySQL接続URLを構築
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}?ssl_ca={DB_SSL_CA}"

if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME, DB_SSL_CA]):
    raise ValueError("Missing database configuration environment variables")

# SQLAlchemyの設定（データベース接続）
try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)  # 接続前にチェックを実施
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except SQLAlchemyError as e:
    logger.error(f"Database connection error: {e}")
    raise RuntimeError(f"Database connection error: {e}")

# ORMの基盤となるクラスを作成
Base = declarative_base()

# CORSの許可設定
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
ALLOWED_ORIGINS_LIST = ALLOWED_ORIGINS.split(",")

# FastAPIアプリの作成
app = FastAPI()

# CORSミドルウェアの追加
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS_LIST,  # 環境変数から取得
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- モデル作成 ---
class Company(Base):
    __tablename__ = "m_user_companies"

    company_id = Column(String(50), primary_key=True)
    company_name = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)
    company_token = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

class Facility(Base):
    __tablename__ = "m_point0_facilities"

    facility_id = Column(String(50), primary_key=True)
    facility_name = Column(String(100), nullable=False)
    facility_type = Column(String(50), nullable=False)
    capacity = Column(Integer, nullable=False)
    location = Column(String(100), nullable=False)
    management_type = Column(String(50), nullable=False)

class Reservation(Base):
    __tablename__ = "t_point0_facility_reservations"

    reservation_id = Column(String(50), primary_key=True)
    company_id = Column(String(50), nullable=False)
    facility_id = Column(String(50), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    attendees = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


# --- Pydantic スキーマ ---
# --- 型チェック大事     ---
class CompanySchema(BaseModel):
    company_id: str
    company_name: str
    company_token: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class FacilitySchema(BaseModel):
    facility_id: str
    facility_name: str
    facility_type: str
    capacity: int
    location: str
    management_type: str

    class Config:
        from_attributes = True

class ReservationSchema(BaseModel):
    reservation_id: str
    company_id: str
    facility_id: str
    start_time: datetime
    end_time: datetime
    attendees: int

    class Config:
        from_attributes = True

class ReservationCreateSchema(BaseModel):
    company_id: str
    facility_id: str
    start_time: datetime
    end_time: datetime
    attendees: int

class ReservationResponseSchema(BaseModel):
    reservation_id: str
    message: str


# データベースセッションを取得する関数
def get_db():
    """データベースセッションを取得し、処理後にクローズする"""
    db = None
    try:
        db = SessionLocal()
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database session error: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        if db:
            db.close()

# ルートエンドポイント
@app.get("/")
def read_root():
    """アプリのルートエンドポイント"""
    return {"message": "Hello, POSTアプリのAdvanceだよ!"}

# --- 1) すべての企業情報を取得 ---
@app.get("/companies", response_model=List[CompanySchema])
def read_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).all()
    return companies

# --- 2) 特定の企業情報を取得 ---
@app.get("/companies/{company_id}", response_model=CompanySchema)
def read_company(company_id: str, db: Session = Depends(get_db)):
    """指定されたユーザーIDの情報を取得"""
    company: Optional[Company] = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="User not found")
    return company  # Pydanticが自動的にJSONへ変換

# --- 3) すべての施設情報を取得 ---
@app.get("/facilities", response_model=List[FacilitySchema])
def read_facilities(db: Session = Depends(get_db)):
    facilities = db.query(Facility).all()
    return facilities

# --- 4) 予約情報を取得 ---
@app.get("/reservations", response_model=List[ReservationSchema])
def get_reservations(
    facility_id: str = Query(..., description="対象施設のID"),
    date: Optional[date] = Query(None, description="予約日 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """ 指定された施設IDと日付の予約情報を取得 """
    try:
        query = db.query(Reservation).filter(Reservation.facility_id == facility_id)

        # `date` が指定された場合、その日付の予約情報を取得
        if date:
            start_of_day = datetime.combine(date, datetime.min.time())
            end_of_day = datetime.combine(date, datetime.max.time())
            query = query.filter(Reservation.start_time >= start_of_day, Reservation.start_time <= end_of_day)

        reservations = query.all()
        return reservations

    except SQLAlchemyError as e:
        logger.error(f"Database query error: {e}")
        raise HTTPException(status_code=500, detail="Database query error")

# --- 5) 予約登録 ---
@app.post("/reservations", response_model=ReservationResponseSchema)
def create_reservation(
    reservation_data: ReservationCreateSchema,
    db: Session = Depends(get_db)
):
    """ 新しい予約を登録する """
    try:
        if reservation_data.start_time >= reservation_data.end_time:
            return {
                "reservation_id": "Error",
                "message": "開始時間は終了時間より前である必要があります。"
            }
        if reservation_data.start_time.minute % 5 != 0 or reservation_data.end_time.minute % 5 != 0:
            return {
                "reservation_id": "Error",
                "message": "開始時間と終了時間は5分単位である必要があります。"
            }
        overlapping_reservations = (
            db.query(Reservation)
            .filter(Reservation.facility_id == reservation_data.facility_id)
            .filter(
                (Reservation.start_time < reservation_data.end_time) &  # 既存の開始時間 < 新しい予約の終了時間
                (Reservation.end_time > reservation_data.start_time)   # 既存の終了時間 > 新しい予約の開始時間
            )
            .all()
        )

        # 予約が被っている場合はエラーを返す
        if overlapping_reservations:
            return {
                "reservation_id": "Error",
                "message": "予約が直前で被りました"
            }

        # 予約IDをUUIDで生成
        reservation_id = str(uuid.uuid4())

        # 予約データを作成
        new_reservation = Reservation(
            reservation_id=reservation_id,
            company_id=reservation_data.company_id,
            facility_id=reservation_data.facility_id,
            start_time=reservation_data.start_time,
            end_time=reservation_data.end_time,
            attendees=reservation_data.attendees,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # データベースに追加
        db.add(new_reservation)
        db.commit()

        return {"reservation_id": reservation_id, "message": "Reservation successfully created."}

    except SQLAlchemyError as e:
        db.rollback()  # エラー発生時はロールバック
        raise HTTPException(status_code=500, detail="Database error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))