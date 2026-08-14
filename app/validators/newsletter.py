from pydantic import BaseModel, EmailStr


class NewsletterSubscribe(BaseModel):
    email: EmailStr
