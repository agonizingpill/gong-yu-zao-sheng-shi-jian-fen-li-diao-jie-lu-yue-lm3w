from pydantic import BaseModel,Field,model_validator

class ReferenceAuthorizationInput(BaseModel):
    granted:bool
    note:str=Field(min_length=6,max_length=300)
    @model_validator(mode='after')
    def stripped(self):
        self.note=self.note.strip()
        if len(self.note)<6:raise ValueError('说明至少6个字')
        return self

class SimilarRecomputeInput(BaseModel):
    min_similarity:float=Field(default=0.90,ge=0.50,le=0.999,allow_inf_nan=False)
    limit:int=Field(default=3,ge=1,le=5)
