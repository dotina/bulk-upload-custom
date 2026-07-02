class UploadError(Exception):
    code = "UPLOAD_ERROR"


class ValidationError(UploadError):
    code = "VALIDATION_ERROR"


class ReferenceNotFoundError(UploadError):
    code = "REFERENCE_NOT_FOUND"


class ApiError(UploadError):
    code = "API_ERROR"

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
