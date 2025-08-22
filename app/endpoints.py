from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.loader import templates
from app.security import authenticate_admin
from app.services import prompt as prompt_service

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(authenticate_admin),
):
    prompts = prompt_service.get_all_prompts(db)
    return templates.TemplateResponse(
        "index.html", {"request": request, "prompts": prompts}
    )


@router.post("/admin/prompt/create")
async def add_prompt(
    name: str = Form(...),
    text: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(authenticate_admin),
):
    prompt_service.create_prompt(db, name, text)
    return RedirectResponse(url="/", status_code=303)


@router.get("/admin/prompt/edit/{prompt_id}", response_class=HTMLResponse)
async def edit_prompt_form(
    prompt_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(authenticate_admin),
):
    prompt = prompt_service.get_prompt_by_id(db, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return templates.TemplateResponse(
        "edit_prompt.html", {"request": request, "prompt": prompt}
    )


@router.post("/admin/prompt/edit/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    name: str = Form(...),
    text: str = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(authenticate_admin),
):
    prompt_service.update_prompt(db, prompt_id, name, text)
    return RedirectResponse(url="/", status_code=303)


@router.post("/admin/prompt/delete/{prompt_id}")
async def delete_prompt_post(
    prompt_id: int, db: Session = Depends(get_db), _: str = Depends(authenticate_admin)
):
    prompt_service.delete_prompt(db, prompt_id)
    return RedirectResponse(url="/", status_code=303)
