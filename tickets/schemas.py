# from pydantic import BaseModel, Field
# from typing import Optional, List
# from uuid import UUID
# from datetime import datetime

# # class TicketCreate(BaseModel):
# #     title: str
# #     description: str | None = None
# #     priority: str


# class TicketCreateSchema(BaseModel):
#     opd_id: UUID
#     category_id: UUID
#     description: str
#     additional_info: Optional[str] = None
#     file_url: Optional[str] = None


# class TicketResponseSchema(BaseModel):
#     message: str
#     ticket_id: UUID
#     status: str

#     class Config:
#         orm_mode = True


# class TicketAttachmentSchema(BaseModel):
#     attachment_id: UUID
#     file_path: str
#     uploaded_at: datetime

#     class Config:
#         orm_mode = True


# class TicketForSeksiSchema(BaseModel):
#     ticket_id: UUID
#     description: Optional[str]
#     priority: Optional[str]
#     status: str
#     created_at: datetime
#     updated_at: Optional[datetime]
#     closed_at: Optional[datetime]
#     opd_id: Optional[UUID]
#     category_id: Optional[UUID]
#     creates_id: Optional[UUID]
#     ticket_source: Optional[str]
#     additional_info: Optional[str]
#     request_type: Optional[str]

#     attachments: List[TicketAttachmentSchema] = []

#     class Config:
#         orm_mode = True


from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from uuid import UUID
from datetime import datetime
from datetime import date

class TicketCreateSchema(BaseModel):
    opd_id: UUID
    # category_id: UUID
    description: str
    additional_info: Optional[str] = None
    priority: Optional[str] = None
    request_type: Optional[str] = None
    ticket_source: Optional[str] = "masyarakat"

    file_urls: Optional[List[str]] = []

class TicketAttachmentSchema(BaseModel):
    attachment_id: UUID
    file_path: str
    uploaded_at: datetime

    class Config:
        orm_mode = True


class TicketResponseSchema(BaseModel):
    message: str
    ticket_id: UUID
    status: str

    class Config:
        orm_mode = True


class TicketForSeksiSchema(BaseModel):
    ticket_id: UUID
    description: Optional[str]
    priority: Optional[str]
    status: str
    ticket_stage: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    closed_at: Optional[datetime]
    opd_id: Optional[UUID]
    # category_id: Optional[UUID]
    creates_id: Optional[UUID]
    ticket_source: Optional[str]
    additional_info: Optional[str]
    request_type: Optional[str]

    asset_aset_id: Optional[int]
    asset_kode_bmd: Optional[str]
    asset_nomor_seri: Optional[str]
    asset_nama: Optional[str]
    asset_kategori: Optional[str]
    asset_subkategori_id: Optional[int]
    asset_jenis: Optional[str]
    asset_lokasi: Optional[dict]
    asset_snapshot: Optional[dict]

    attachments: List[TicketAttachmentSchema] = []

    class Config:
        orm_mode = True


class TicketTrackResponse(BaseModel):
    ticket_id: UUID
    status: str
    jenis_laporan: Optional[str] = None
    opd: Optional[str] = None

    class Config:
        orm_mode = True



class TicketCategorySchema(BaseModel):
    category_id: UUID
    opd_id: UUID
    category_name: str
    description: Optional[str]

    class Config:
        orm_mode = True

class UpdatePriority(BaseModel):
    urgency: int = Field(..., ge=1, le=3)
    impact: int = Field(..., ge=1, le=3)

class ManualPriority(BaseModel):
    priority: Literal["Low", "Medium", "High", "Critical"]


class RejectReasonSeksi(BaseModel):
    reason: str

class RejectReasonBidang(BaseModel):
    reason: str

class AssignTeknisiSchema(BaseModel):
    teknisi_id: UUID
    pengerjaan_awal: date
    pengerjaan_akhir: date
    incident_repeat_flag: bool = False

class WarRoomCreate(BaseModel):
    ticket_id: UUID
    title: str
    link_meet: Optional[str]
    start_time: datetime
    end_time: datetime
    opd_ids: List[int]
    seksi_ids: List[UUID]

class ServiceRequestCreate(BaseModel):
    unit_kerja_id: int
    lokasi_id: int
    nama_aset_baru: str
    kategori_aset: str    
    subkategori_id: int
    metadata: Optional[dict] = None

# class RFCIncidentRepeatSchema(BaseModel):
#     judul_perubahan: str
#     kategori_aset: str
#     id_aset: int
#     deskripsi_aset: str
#     alasan_perubahan: str
#     dampak_perubahan: str
#     dampak_jika_tidak: str
#     biaya_estimasi: int
#     nama_pemohon: str
#     opd_pemohon: str
#     risk_score_aset: int = 0


class RFCIncidentRepeatSchema(BaseModel):
    judul_perubahan: str
    id_aset: int
    deskripsi_aset: str 
    alasan_perubahan: str
    dampak_perubahan: str
    dampak_jika_tidak: str
    biaya_estimasi: int

class RFCChangeRequestSchema(BaseModel):
    ticket_id: UUID               
    judul_perubahan: str
    id_aset: int
    deskripsi_aset: str
    alasan_perubahan: str
    dampak_perubahan: str
    dampak_jika_tidak: str
    biaya_estimasi: int


# class TicketTrackResponse(BaseModel):
#     ticket_id: UUID 
#     status: str 
#     jenis_laporan: Optional[str]
#     opd: Optional[str]

#     class Config:
#         orm_mode = True
