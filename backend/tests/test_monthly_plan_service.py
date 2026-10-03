from app.monthly_plan_service import group_for,normalized

def test_real_plan_groups_liability_account_types():
    assert group_for("mortgage")=="Mortgage"
    assert group_for("credit_card")=="Credit Cards"
    assert group_for("auto_loan")=="Loans"
    assert group_for("other")=="Taxes and Other Debt"

def test_plan_name_matching_ignores_spacing_and_punctuation():
    assert normalized("PayPal Mastercard") == normalized("PayPal-Mastercard")
