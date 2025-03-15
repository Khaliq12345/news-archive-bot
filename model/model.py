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
    age: int | None = Field(
        alias="Age",
        description="Extract the age of the suspect, return None if not found",
    )
    officer_involved: str | None = Field(
        alias="Officer Involved",
        description="Extract the name of the officer involved, return None if not found",
    )
    location: str | None = Field(
        alias="Location",
        description="Extract the location of the incident, return None if not found",
    )
    department: str | None = Field(
        alias="Department",
        description="Extract the department of the incident, return None if not found",
    )
    state: str | None = Field(
        alias="State",
        description="Extract the state of the incident, return None if not found",
    )
    year: int = Field(alias="Year", description="Extract the year of the article")
    charge: str | None = Field(
        alias="Charge", description="Extract the charge of the suspect in the article"
    )
