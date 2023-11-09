import dataclasses
import json
import time
import logging
from dataclasses import dataclass, field
from django.conf import settings as django_settings
from django.utils import timezone
from django.core.exceptions import ImproperlyConfigured, MiddlewareNotUsed

from drf_api_logger import API_LOGGER_SIGNAL
from drf_api_logger.start_logger_when_server_starts import LOGGER_THREAD
from drf_api_logger.utils import get_headers, get_client_ip, mask_sensitive_data
from drf_api_logger.middleware.filters import APILogFilter

logger = logging.getLogger(__name__)
log_prefix = "######->>"


@dataclass
class APILoggerSettings:
    DATABASE: bool = False
    SIGNAL: bool = False
    PATH_TYPE: str = 'ABSOLUTE'
    METHODS: list | tuple = field(default_factory=list)
    STATUS_CODES: list | tuple = field(default_factory=list)
    SKIP_URL_NAME: list | tuple = field(default_factory=list)  # TODO: To be deprecated to SKIP_URL_NAMES
    SKIP_NAMESPACE: list | tuple = field(default_factory=list)  # TODO: To be deprecated to SKIP_URL_NAMESPACES


class APILoggerMiddleware:
    def __init__(self, get_response):
        logger.debug(f"{log_prefix} Initiating DRF-API-Logger")
        self.get_response = get_response

        # TODO: Voir pour raise une exception pour les params qui sont donnés avec un mauvais type
        django_settings_prefix = "DRF_API_LOGGER"
        config = {}
        for _field in dataclasses.fields(APILoggerSettings):
            setting_name = f"{django_settings_prefix}_{_field.name}"
            setting_value = getattr(django_settings, setting_name, None)
            if setting_value is not None:
                config[_field.name] = setting_value

        self.settings = APILoggerSettings(**config)

        if not self.settings.DATABASE and not self.settings.SIGNAL:
            # Run only if logger is enabled (raising will deregister us from the middleware process)
            raise MiddlewareNotUsed()

        allowed_path_type = ['ABSOLUTE', 'RAW_URI', 'FULL_PATH']
        if self.settings.PATH_TYPE not in allowed_path_type:
            raise ImproperlyConfigured(
                f"[DRF-API-LOGGER] {django_settings_prefix}_PATH_TYPE should be one of the following:"
                f" {','.join(allowed_path_type)}"
            )

        # Method to call on the request object to get the url logged as the user wants it
        resolver_from_path_type = {
            "ABSOLUTE": "build_absolute_uri",
            "FULL_PATH": "get_full_path",
            "RAW_URI": "get_raw_uri",
        }
        self.request_resolver_callable_name = resolver_from_path_type[self.settings.PATH_TYPE]

        self.api_call_filter = APILogFilter(self.settings)

        # TODO: Raise in case METHODS ne sont pas dans les méthodes HTTP connues

    def __call__(self, request):
        # We require the final response to check if it should be filtered or not,
        # so we can generate it from the start.
        logger.debug(f"{log_prefix} New API call...")
        start_time = time.time()
        response = self.get_response(request)
        execution_time = time.time() - start_time

        if self.api_call_filter.is_filtered(request, response):
            logger.debug(f"{log_prefix} API call filtered - Returning")
            return response

        request_data = ''
        try:
            request_data = json.loads(request.body) if request.body else ''
        except Exception:
            pass

        if getattr(response, 'streaming', False):
            response_body = '** Streaming **'
        else:
            response_body = json.loads(response.content)

        headers = get_headers(request=request)
        api_call_url = getattr(request, self.request_resolver_callable_name)()
        data = dict(
            api=api_call_url,
            headers=mask_sensitive_data(headers),
            body=mask_sensitive_data(request_data),
            method=request.method,
            client_ip_address=get_client_ip(request),
            response=mask_sensitive_data(response_body),
            status_code=response.status_code,
            execution_time=execution_time,
            added_on=timezone.now()
        )
        if self.settings.DATABASE:
            if LOGGER_THREAD:
                d = data.copy()
                d['headers'] = json.dumps(d['headers'], indent=4, ensure_ascii=False)
                if request_data:
                    d['body'] = json.dumps(d['body'], indent=4, ensure_ascii=False)
                d['response'] = json.dumps(d['response'], indent=4, ensure_ascii=False)
                LOGGER_THREAD.put_log_data(data=d)
        if self.settings.SIGNAL:
            API_LOGGER_SIGNAL.listen(**data)

        return response