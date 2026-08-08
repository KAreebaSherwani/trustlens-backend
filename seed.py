"""Realistic seed applicants so the officer dashboard and garden are populated on first load."""
from models import OnboardingIn

SEED = [
    dict(name="Sara Bilal", cnic="61101-1111111-1", city="Islamabad", employment_type="Salaried",
         monthly_income=120000, account_purpose="Salary and personal use",
         expected_monthly_transactions=110000, business_type=""),
    dict(name="Ahmed Raza", cnic="35202-2222222-2", city="Lahore", employment_type="Salaried",
         monthly_income=90000, account_purpose="Personal savings",
         expected_monthly_transactions=60000, business_type=""),
    dict(name="Kamran Ahmed", cnic="37405-3333333-3", city="Rawalpindi", employment_type="Self-employed",
         business_type="Electronics shop", monthly_income=70000,
         account_purpose="Receive customer payments", expected_monthly_transactions=1000000),
    dict(name="Fatima Noor", cnic="42101-4444444-4", city="Karachi", employment_type="Self-employed",
         business_type="Online clothing store", monthly_income=90000,
         account_purpose="Receive customer payments", expected_monthly_transactions=650000),
    dict(name="Bilal Khan", cnic="17301-5555555-5", city="Peshawar", employment_type="Student",
         monthly_income=0, account_purpose="Personal use",
         expected_monthly_transactions=1500000, business_type=""),
    dict(name="Zainab Ali", cnic="33100-6666666-6", city="Faisalabad", employment_type="Unemployed",
         monthly_income=200000, account_purpose="Personal savings",
         expected_monthly_transactions=900000, business_type=""),
    dict(name="Usman Tariq", cnic="36302-7777777-7", city="Multan", employment_type="Salaried",
         monthly_income=150000, account_purpose="Personal use",
         expected_monthly_transactions=140000, business_type=""),
    dict(name="Ayesha Malik", cnic="61101-8888888-8", city="Islamabad", employment_type="Self-employed",
         business_type="Home bakery", monthly_income=60000,
         account_purpose="Receive customer payments", expected_monthly_transactions=200000),
]


def seed(create_application):
    for s in SEED:
        create_application(OnboardingIn(**s))