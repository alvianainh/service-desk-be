from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from auth.auth import get_current_user, get_current_user_universal
from auth.database import get_db
from auth.models import Articles, Users, ArticleTags, Tags, Roles
import uuid
from pydantic import BaseModel
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
import os
import mimetypes
from uuid import uuid4
from supabase import create_client
from datetime import datetime
from tickets.models import Announcements, Notifications

router = APIRouter(prefix="/articles", tags=["articles"])

class ArticleCreate(BaseModel):
    title: str
    content: str
    tags: Optional[List[str]] = []
    cover_url: Optional[str] = None

class ArticleData(BaseModel):
    article_id: UUID
    title: str
    status: str
    cover_path: Optional[str]
    tags: List[str] = []
    created_at: datetime
    status_admin_opd: Optional[str]   
    status_admin_kota: Optional[str] 



    class Config:
        orm_mode = True


class ArticleResponse(BaseModel):
    message: str
    data: ArticleData

class ArticleUpdate(BaseModel):
    title: str
    content: str

#tags
class TagCreate(BaseModel):
    tag_name: str


class TagResponse(BaseModel):
    tag_id: UUID
    tag_name: str

    class Config:
        orm_mode = True



SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


#TAGS
@router.post("/tags", response_model=TagResponse)
async def create_tag(
    data: TagCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal) 
):
    if current_user.get("role_name") != "admin dinas":
        raise HTTPException(status_code=403, detail="Unauthorized: Only admin_opd can create tags")

    existing_tag = db.query(Tags).filter(Tags.tag_name == data.tag_name).first()
    if existing_tag:
        raise HTTPException(status_code=400, detail="Tag dengan nama ini sudah ada")

    new_tag = Tags(tag_name=data.tag_name)
    db.add(new_tag)
    db.commit()
    db.refresh(new_tag)

    return new_tag



@router.get("/tags", response_model=List[TagResponse])
async def get_all_tags(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    tags = db.query(Tags).order_by(Tags.tag_name.asc()).all()
    return tags


@router.post("/", response_model=ArticleResponse)
async def create_article(
    title: str = Form(...),
    content: str = Form(...),
    tag_ids: Optional[List[str]] = Form(None),
    cover_url: Optional[str] = Form(None),
    cover_file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    roles = current_user.get("role_name", [])
    if "admin dinas" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only admin dinas can create articles")

    if not cover_file and not cover_url:
        raise HTTPException(status_code=400, detail="Harus menyertakan file cover atau URL cover")

    final_cover_path = cover_url

    if cover_file:
        try:
            file_ext = os.path.splitext(cover_file.filename)[1]
            file_name = f"{uuid4()}{file_ext}"
            file_bytes = await cover_file.read()
            content_type = mimetypes.guess_type(cover_file.filename)[0] or "application/octet-stream"

            res = supabase.storage.from_("cover_article").upload(
                file_name, file_bytes, {"content-type": content_type}
            )

            if hasattr(res, "error") and res.error:
                raise Exception(res.error.message)
            if isinstance(res, dict) and res.get("error"):
                raise Exception(res["error"])

            file_url = supabase.storage.from_("cover_article").get_public_url(file_name)
            final_cover_path = file_url if isinstance(file_url, str) else cover_url
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cover upload failed: {str(e)}")

    new_article = Articles(
        title=title,
        content=content,
        status="pending_review",         
        status_admin_opd="menunggu review",  
        status_admin_kota="draft",       
        makes_by_id=current_user["id"],
        cover_path=final_cover_path
    )
    db.add(new_article)
    db.commit()
    db.refresh(new_article)

    if tag_ids:
        for tag_id in tag_ids:
            tag = db.query(Tags).filter(Tags.tag_id == tag_id).first()
            if not tag:
                raise HTTPException(status_code=404, detail=f"Tag dengan ID {tag_id} tidak ditemukan")
            new_article.tags.append(tag) 

    db.commit()
    db.refresh(new_article)

    tag_names = [t.tag_name for t in new_article.tags]
    admin_kotas = (
        db.query(Users)
        .join(Roles, Users.role_id == Roles.role_id)
        .filter(Roles.role_name == "diskominfo")
        .all()
    )

    notif_message = f"Artikel '{new_article.title}' telah diajukan dan menunggu review admin kota"

    for admin in admin_kotas:
        new_notif = Notifications(
            id=uuid4(),
            user_id=admin.id,  # user admin kota
            article_id=new_article.article_id,
            notification_type="article",
            message=notif_message,
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.add(new_notif)

    db.commit()

    return {
        "message": "Artikel berhasil diajukan dan menunggu review admin kota",
        "data": {
            "article_id": str(new_article.article_id),
            "title": new_article.title,
            "status": new_article.status,
            "cover_path": new_article.cover_path,
            "tags": tag_names,
            "created_at": new_article.created_at,
            "status_admin_opd": new_article.status_admin_opd,
            "status_admin_kota": new_article.status_admin_kota
        }
    }


@router.put("/{article_id}", response_model=dict)
async def update_article(
    article_id: str,
    data: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    roles = current_user.get("role_name", [])

    if "admin dinas" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: Only admin dinas can update articles"
        )

    article = db.query(Articles).filter(Articles.article_id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if str(article.makes_by_id) != current_user["id"]:
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own articles"
        )

    if article.status in ["approved", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit article that has been approved by admin_kota"
        )

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


@router.put("/{article_id}/verify")
async def verify_article(
    article_id: str,
    decision: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    roles = current_user.get("role_name", [])


    if "diskominfo" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: Only admin_kota can verify articles"
        )

    current_user_id = current_user["id"]

    article = db.query(Articles).filter(Articles.article_id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    valid_decisions = ["review", "approve", "reject"]
    if decision not in valid_decisions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision. Must be one of {valid_decisions}"
        )

    # Aturan final status
    if article.status in ["approved", "rejected"]:
        # Tidak bisa diubah lagi
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change article status. Article has already been {article.status}"
        )

    now = datetime.utcnow()
    notif_message = None

    if decision == "review":
        article.status_admin_kota = "review"
        article.status = "review"
        notif_message = f"Artikel '{article.title}' dikembalikan ke status review oleh admin kota"

    elif decision == "approve":
        article.status_admin_kota = "approved"
        article.status = "approved"
        article.status_admin_opd = "approved"
        article.approved_id = current_user["id"]
        notif_message = f"Artikel '{article.title}' telah disetujui oleh admin kota"

    elif decision == "reject":
        article.status_admin_kota = "rejected"
        article.status = "rejected"
        article.status_admin_opd = "rejected"
        article.approved_id = current_user["id"]
        notif_message = f"Artikel '{article.title}' ditolak oleh admin kota"

    db.commit()
    db.refresh(article)

    if notif_message and article.makes_by_id:
        new_notif = Notifications(
            id=uuid4(),
            user_id=article.makes_by_id,
            article_id=article.article_id,  
            notification_type="article",
            message=notif_message,
            is_read=False,
            created_at=now
        )
        db.add(new_notif)
        db.commit()

    return {
        "message": f"Article status has been updated to '{article.status}'",
        "data": {
            "article_id": str(article.article_id),
            "status": article.status,
            "status_admin_kota": article.status_admin_kota,
            "status_admin_opd": article.status_admin_opd,
            "approved_id": str(article.approved_id) if article.approved_id else None
        }
    }

@router.put("/{article_id}/publish")
async def publish_article(
    article_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    # Cek role admin kota
    roles = current_user.get("role_name", [])
    if "diskominfo" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: Only admin_kota can publish articles"
        )
    
    current_user_id = current_user["id"]

    article = db.query(Articles).filter(Articles.article_id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if article.status not in ["approved"]:
        raise HTTPException(
            status_code=400,
            detail="Article must be approved before publishing"
        )
    
    article.status = "published"
    article.status_admin_kota = "published"
    article.status_admin_opd = "published"

    db.commit()
    db.refresh(article)

    admin_kotas = db.query(Users).join(Roles, Roles.role_id == Users.role_id)\
                    .filter(Roles.role_name == "diskominfo").all()

    notif_message = f"Artikel '{article.title}' telah dipublikasikan"

    for admin in admin_kotas:
        new_notif = Notifications(
            id=uuid4(),
            user_id=admin.id,   
            article_id=article.article_id,
            notification_type="article",
            message=notif_message,
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.add(new_notif)

    db.commit()

    return {
        "message": f"Article has been published",
        "data": {
            "article_id": str(article.article_id),
            "status": article.status,
            "status_admin_kota": article.status_admin_kota,
            "status_admin_opd": article.status_admin_opd
        }
    }


@router.get("/", response_model=list)
async def get_public_articles(db: Session = Depends(get_db)):
    articles = (
        db.query(Articles)
        .filter(Articles.status == "published")
        .order_by(Articles.created_at.desc())
        .all()
    )

    results = []
    for a in articles:
        tags_data = [
            {"tag_id": str(tag.tag_id), "tag_name": tag.tag_name}
            for tag in a.tags
        ]

        author_data = None
        if a.makes_by:
            author_data = {
                "user_id": str(a.makes_by.id),
                "full_name": a.makes_by.full_name,
                "email": a.makes_by.email
            }

        results.append({
            "article_id": str(a.article_id),
            "title": a.title,
            "content": a.content,
            "cover_path": a.cover_path,
            "tags": tags_data,
            "author": author_data
        })

    return results


@router.get("/my-articles")
async def get_my_articles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    articles = (
        db.query(Articles)
        .filter(Articles.makes_by_id == current_user["id"])
        .order_by(Articles.updated_at.desc())
        .all()
    )
    results = []
    for a in articles:
        tags_data = [
            {"tag_id": str(tag.tag_id), "tag_name": tag.tag_name}
            for tag in a.tags
        ]

        results.append({
            "article_id": str(a.article_id),
            "title": a.title,
            "status": a.status,
            "cover_path": a.cover_path,
            "updated_at": a.updated_at,
            "tags": tags_data
        })

    return {
        "total": len(results),
        "data": results
    }

@router.get("/articles/{article_id}")
async def get_article_detail(
    article_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    article = (
        db.query(Articles)
        .filter(Articles.article_id == article_id)
        .first()
    )

    if not article:
        raise HTTPException(
            status_code=404,
            detail="Artikel tidak ditemukan."
        )

    tags_data = [
        {"tag_id": str(tag.tag_id), "tag_name": tag.tag_name}
        for tag in article.tags
    ]

    author = article.makes_by if hasattr(article, "makes_by") else None

    return {
        "status": "success",
        "data": {
            "article_id": str(article.article_id),
            "title": article.title,
            "content": article.content,
            "status": article.status,
            "cover_path": article.cover_path,
            "created_at": article.created_at,
            "updated_at": article.updated_at,
            "tags": tags_data,
            "author": {
                "id": str(author.id) if author else None,
                "name": author.full_name if author else None,
                "email": author.email if author else None
            }
        }
    }




@router.get("/all", response_model=dict)
async def get_all_articles(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_universal)
):
    roles = current_user.get("role_name", [])
    if "diskominfo" not in roles:
        raise HTTPException(status_code=403, detail="Unauthorized: Only admin_kota can access this data")

    articles = (
        db.query(Articles)
        .order_by(Articles.created_at.desc())
        .all()
    )

    results = []
    for a in articles:
        tags_data = [
            {"tag_id": str(tag.tag_id), "tag_name": tag.tag_name}
            for tag in a.tags
        ]

        results.append({
            "article_id": str(a.article_id),
            "user_id": str(a.makes_by_id),
            "title": a.title,
            "content": a.content,
            "status": a.status,
            "cover_path": a.cover_path,
            "created_at": a.created_at,
            "tags": tags_data,
            "status_admin_kota": a.status_admin_kota
        })

    return {
        "total": len(results),
        "data": results
    }