import pandas as pd
from core.contracts.dataset import DatasetContract, FieldContract
from data.validation.validator import DataValidator

def test_required_and_range_validation():
    c=DatasetContract("x", (FieldContract("tonnes","mass","tonne",False,0),), ("id",))
    df=pd.DataFrame({"id":[1,2],"tonnes":[10,-1]})
    r=DataValidator().validate(df,c)
    assert not r.passed
    assert any(i.code == "MIN_RANGE" for i in r.issues)
