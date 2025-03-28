from pydantic import BaseModel, Field


class Single_ListingPage_Article(BaseModel):
    title: str | None = Field(
        alias="Title",
        description="Extract the title of the article, return None if not found",
    )
    url: str | None = Field(
        alias="URL",
        description="Extract the URL of the article, return None if not found",
    )
    date: str | None = Field(
        alias="Date",
        description="Extract the date of the article, return None if not found",
    )


class Multi_ListingPage_Article(BaseModel):
    data: list[Single_ListingPage_Article]


class DetailPage(BaseModel):
    title: str | None = Field(
        alias="Title",
        description="Extract the title of the article, return None if not found",
    )
    date: str | None = Field(
        alias="Date",
        description="Extract the full date of the article in format YYYY-MM-DD",
    )
    content: str | None = Field(
        alias="Content",
        description="Use the content of the article to provide summary, return None if not found",
    )
    suspect_name: str | None = Field(
        alias="Suspect Name",
        description="Extract the name of the suspect, return None if not found",
    )
    charge: str | None = Field(
        alias="Charge", description="Extract the charge of the suspect in the article"
    )
