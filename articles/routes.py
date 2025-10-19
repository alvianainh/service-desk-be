from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth.auth import get_current_user
from auth.database import get_db
from auth.models import Articles, Users
import uuid
from pydantic import BaseModel
from sqlalchemy import func


router = APIRouter(prefix="/articles", tags=["Articles"])

class ArticleCreate(BaseModel):
    title: str
    content: str

class ArticleUpdate(BaseModel):
    title: str
    content: str

@router.post("/", response_model=dict)
async def create_article(
    data: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])

    # Hanya admin_opd yang boleh membuat artikel
    if "admin_opd" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only admin_opd can create articles")

    new_article = Articles(
        title=data.title,
        content=data.content,
        status="pending_review",
        makes_by_id=current_user["id"]
    )

    db.add(new_article)
    db.commit()
    db.refresh(new_article)

    return {
        "message": "Artikel berhasil diajukan dan menunggu review admin kota",
        "data": {
            "article_id": str(new_article.article_id),
            "title": new_article.title,
            "status": new_article.status,
            "created_at": new_article.created_at
        }
    }

@router.put("/{article_id}", response_model=dict)
async def update_article(
    article_id: str,
    data: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])

    # Hanya admin_opd yang boleh update artikel
    if "admin_opd" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: Only admin_opd can update articles"
        )

    # Cari artikel berdasarkan ID
    article = db.query(Articles).filter(Articles.article_id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Pastikan artikel dibuat oleh user yang sedang login
    if str(article.makes_by_id) != current_user["id"]:
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own articles"
        )

    # Jika sudah di-approve oleh admin_kota, tidak boleh diedit
    if article.status in ["approved", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit article that has been approved by admin_kota"
        )

    # Update field yang boleh diubah
    article.title = data.title
    article.content = data.content
    article.updated_at = func.now()

    db.commit()
    db.refresh(article)

    return {
        "message": "Artikel berhasil diperbarui",
        "data": {
            "article_id": str(article.article_id),
            "title": article.title,
            "content": article.content,
            "status": article.status,
            "updated_at": article.updated_at
        }
    }


#UPDATE APPROVE REJECT DUA ARAH
# @router.put("/{article_id}/verify")
# async def verify_article(
#     article_id: str,
#     decision: str,  # "approve" atau "reject"
#     db: Session = Depends(get_db),
#     current_user: dict = Depends(get_current_user)
# ):
#     roles = current_user.get("roles", [])

#     if "admin_kota" not in roles:
#         raise HTTPException(status_code=403, detail="Unauthorized: Only admin_kota can verify articles")

#     article = db.query(Articles).filter(Articles.article_id == article_id).first()
#     if not article:
#         raise HTTPException(status_code=404, detail="Article not found")

#     if decision not in ["approve", "reject"]:
#         raise HTTPException(status_code=400, detail="Invalid decision. Must be 'approve' or 'reject'")

#     article.status = "approved" if decision == "approve" else "rejected"
#     article.approved_id = current_user["id"]
#     db.commit()

#     return {"message": f"Article has been {article.status}"}


# UPDATE APPROVAL SATU ARAH
@router.put("/{article_id}/verify")
async def verify_article(
    article_id: str,
    decision: str,  # "approve" atau "reject"
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    roles = current_user.get("roles", [])

    if "admin_kota" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only admin_kota can verify articles")

    article = db.query(Articles).filter(Articles.article_id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if decision not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid decision. Must be 'approve' or 'reject'")

    # Cek jika artikel sudah diverifikasi sebelumnya
    if article.status in ["approved", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change article status. Article has already been {article.status}"
        )

    article.status = "approved" if decision == "approve" else "rejected"
    article.approved_id = current_user["id"]
    db.commit()
    db.refresh(article)

    return {"message": f"Article has been {article.status}"}


# Lihat semua artikel yang sudah diverifikasi
@router.get("/", response_model=list)
async def get_public_articles(db: Session = Depends(get_db)):
    articles = db.query(Articles).filter(Articles.status == "approved").all()
    return [{"title": a.title, "content": a.content, "author": f"{a.makes_by.first_name} {a.makes_by.last_name}"} for a in articles]


# Lihat artikel milik admin_opd sendiri
@router.get("/my-articles")
async def get_my_articles(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    articles = db.query(Articles).filter(Articles.makes_by_id == current_user["id"]).all()
    return [{"title": a.title, "status": a.status, "updated_at": a.updated_at} for a in articles]



@router.get("/all", response_model=dict)
async def get_all_articles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Pastikan hanya admin_kota yang bisa akses
    roles = current_user.get("roles", [])
    if "admin_kota" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only admin_kota can access this data")

    # Ambil semua artikel dari admin_opd
    articles = (
        db.query(Articles)
        .order_by(Articles.created_at.desc())
        .all()
    )

    # Format hasilnya
    results = [
        {
            "article_id": str(a.article_id),
            "user_id": str(a.makes_by_id),
            "title": a.title,
            "content": a.content,
            "status": a.status,
            "created_at": a.created_at,
        }
        for a in articles
    ]

    return {"total": len(results), "data": results}
