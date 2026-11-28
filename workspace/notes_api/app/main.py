from typing import List

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Note(BaseModel):
    id: int
    content: str


notes_db = []


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/notes", response_model=Note)
async def create_note(note: Note):
    notes_db.append(note)
    return note


@app.get("/notes", response_model=List[Note])
async def get_notes():
    return notes_db
