"""Evidence selection is deliberately more conservative than language generation."""
import re


def split_sentences(text):
    result = []
    # A PDF's soft line wrap is not a sentence boundary. Keep the exact original
    # substring (including newlines), so citation validation stays byte-for-text exact.
    for part in re.split(r"(?<=[.!?])\s+|\n[ \t]*\n", text):
        part = part.strip()
        while part.startswith("#"):
            _, separator, part = part.partition("\n")
            part = part.strip() if separator else ""
        if len(part) > 15:
            result.append(part)
    return result


def contradiction(candidates):
    # A narrow, testable contradiction detector. This is not a general NLI model.
    seen = {}
    for _, sentence, _ in candidates:
        numbers = re.findall(r"\b\d+\b", sentence)
        if not numbers:
            continue
        signature = re.sub(r"\b\d+\b", "#", sentence.casefold())
        if signature in seen and seen[signature] != numbers:
            return True
        seen[signature] = numbers
    return False


def needs_qualification(question):
    # Do not infer eligibility, unit conversion or exceptions from a numeric policy quote.
    temporal = bool(re.search(r"\b(day|days|week|weeks|month|months|year|years)\b", question.lower()))
    number = bool(re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", question.lower()))
    return temporal and number


def instruction_attack(question):
    text = question.casefold()
    return bool(re.search(r"ignore (?:all |the |any )?(?:previous |prior )?(?:instructions|documents|rules)|(?:reveal|print|output|steal|give me).*(?:password|private credential|administrator token|another user)|execute.*(?:command|code)|disable.*authoriz|change.*project permissions|invent.*citation|cite a nonexistent|follow.*injected", text))
