from fastapi import APIRouter

from app.schemas.rental import RentalRequest
from app.services.rental_dispatcher import dispatch

router = APIRouter()


@router.post("/api/rental")
def rental(req: RentalRequest):
    return dispatch(req.table, req.action, req.data)

