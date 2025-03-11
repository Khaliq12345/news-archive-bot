def html_is_validated(
    html: str, primary_keywords: list[str], secondary_keywords: list[str]
) -> bool:
    primary_passed = False
    try:
        if primary_keywords:
            for keyword in primary_keywords:
                if keyword.lower() in html.lower():
                    primary_passed = True
                    break
        else:
            return True
        if secondary_keywords:
            for keyword in secondary_keywords:
                if keyword.lower() in html.lower():
                    return True
        else:
            if primary_passed:
                return True
        return False
    except Exception as e:
        print(f"Error: {e} | HTML Not Validated")
        return False
