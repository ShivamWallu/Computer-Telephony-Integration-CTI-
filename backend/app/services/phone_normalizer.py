import re
from typing import Optional, List, Tuple
from backend.app.config import settings

class PhoneNormalizer:
    """
    High-performance phone number cleaner, normalizer, and variant generator
    specifically engineered for CTI lookup, duplicate detection, and indexed searches.
    Guarantees seamless matching whether country codes are present or omitted.
    """

    @staticmethod
    def clean_digits(phone_str: Optional[str]) -> str:
        """Extract only numeric digits from string."""
        if not phone_str:
            return ""
        return re.sub(r"\D", "", str(phone_str))

    @classmethod
    def normalize(cls, phone_str: Optional[str], default_country_code: str = settings.DEFAULT_COUNTRY_CODE) -> str:
        """
        Normalize any raw phone number into a canonical indexed search key.
        Handles missing country codes, extra zeros, leading pluses, spaces, and dashes.
        For Indian numbers (10 digits):
          - "+91 78147 49816" -> "7814749816"
          - "07814749816"     -> "7814749816"
          - "917814749816"    -> "7814749816"
          - "7814749816"      -> "7814749816"
          - "78147-49816"     -> "7814749816"
        """
        digits = cls.clean_digits(phone_str)
        if not digits:
            return ""

        # Check standard Indian phone patterns (or default country code)
        if default_country_code == "91":
            # 12 digits starting with 91 -> 10 digits
            if len(digits) == 12 and digits.startswith("91"):
                return digits[2:]
            # 11 digits starting with 0 -> 10 digits
            if len(digits) == 11 and digits.startswith("0"):
                return digits[1:]
            # 10 digits standard mobile/landline
            if len(digits) == 10:
                return digits

        # General international handling: if starts with double zero (00), strip it
        if digits.startswith("00"):
            digits = digits[2:]

        return digits

    @classmethod
    def get_search_variants(cls, query_str: str) -> List[str]:
        """
        Generate all plausible indexed variations of a searched phone string
        to enable instant index hits via SQL 'IN (:variants)'.
        """
        digits = cls.clean_digits(query_str)
        if not digits:
            return []

        variants = set()
        variants.add(digits)

        normalized = cls.normalize(query_str)
        if normalized:
            variants.add(normalized)
            # Add country code prepended variant
            variants.add(f"91{normalized}")
            variants.add(f"+91{normalized}")
            variants.add(f"+91 {normalized}")
            # Add leading zero variant
            variants.add(f"0{normalized}")

        # If digits start with 91, also add without 91
        if digits.startswith("91") and len(digits) > 10:
            variants.add(digits[2:])
        # If digits start with 0, also add without 0
        if digits.startswith("0") and len(digits) > 10:
            variants.add(digits[1:])

        return list(variants)

    @classmethod
    def format_display(cls, phone_str: Optional[str], country_code: str = "+91") -> str:
        """Format normalized phone for clean, readable CRM display."""
        if not phone_str:
            return ""
        
        # If string already has custom formatting or international prefix
        s = str(phone_str).strip()
        norm = cls.normalize(s)
        
        if len(norm) == 10:
            cc = country_code if country_code else "+91"
            if not cc.startswith("+"):
                cc = f"+{cc}"
            return f"{cc} {norm[:5]} {norm[5:]}"
        elif len(norm) == 11 and norm.startswith("0"):
            return f"0{norm[1:6]} {norm[6:]}"
        elif len(norm) > 10:
            return f"+{norm}"
        return s
