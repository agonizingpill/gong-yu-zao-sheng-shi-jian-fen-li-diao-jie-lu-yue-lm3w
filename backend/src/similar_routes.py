from fastapi import APIRouter,Depends
from .database import session
from .auth import current,supervisor
from .similar_schemas import ReferenceAuthorizationInput,SimilarRecomputeInput
from . import similar_service as service
router=APIRouter()
@router.get('/complaints/{id}/reference-authorization')
def authorization(id:int,db=Depends(session),u=Depends(current)):return service.authorization(db,id)
@router.post('/complaints/{id}/reference-authorization')
def authorize(id:int,data:ReferenceAuthorizationInput,db=Depends(session),u=Depends(supervisor)):return service.authorize(db,u,id,data)
@router.get('/complaints/{id}/similar-cases')
def similar(id:int,db=Depends(session),u=Depends(current)):return service.current(db,id)
@router.post('/complaints/{id}/similar-cases/recompute')
def recompute(id:int,data:SimilarRecomputeInput,db=Depends(session),u=Depends(supervisor)):return service.recompute(db,u,id,data)
@router.get('/similar-cases/{reference}/practices')
def practices(reference:int,db=Depends(session),u=Depends(current)):return service.practices(db,u,reference)
