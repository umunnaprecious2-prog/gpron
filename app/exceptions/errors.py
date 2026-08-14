"""Named domain exceptions, replacing scattered ad-hoc HTTPException calls.

Routes/services raise these; app/exceptions/handlers.py translates them into
consistent JSON error responses.
"""


class AppError(Exception):
    status_code: int = 500

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class NotFoundError(AppError):
    status_code = 404


class UnauthorizedError(AppError):
    status_code = 401


class ForbiddenError(AppError):
    status_code = 403


class ConflictError(AppError):
    status_code = 400
