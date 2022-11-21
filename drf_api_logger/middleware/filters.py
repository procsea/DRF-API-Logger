from typing import TYPE_CHECKING

from django.urls import resolve

if TYPE_CHECKING:
    from api_logger_middleware import APILoggerSettings
    from django.urls.resolvers import ResolverMatch


class APILogFilter:
    """This class is extendable as you can simply add a new method to validate... blabla
    If you want to add new filters, please do it here so they can be dynamically used depending on
    the user settings.
    """
    def __init__(self, settings: APILoggerSettings):
        self.settings = settings
        self.current_request = None
        self.current_response = None
        self.__current_resolver_match: ResolverMatch | None = None

        self.filter_methods = [
            "_is_filtered_by_content_type",
            "_is_filtered_by_admin_namespace"
        ]
        setting_conditioned_filters = {
            self.settings.SKIP_URL_NAME: "_is_filtered_by_url_names_skipped",
            self.settings.SKIP_NAMESPACE: "_is_filtered_by_namespaces_skipped",
            self.settings.METHODS: "_is_filtered_by_http_method",
            self.settings.STATUS_CODES: "_is_filtered_by_status_code",
        }
        for setting, filter_method_name in setting_conditioned_filters.items():
            if setting:
                self.filter_methods.append(filter_method_name)

    def is_filtered(self, request, response):
        self.current_request = request
        self.current_response = response
        try:
            for filter in self.filter_methods:
                if getattr(self, filter)():
                    return True
        finally:
            self.current_request = None
            self.current_response = None
            self.__current_resolver_match = None
        return False

    @property
    def _resolver_match(self) -> ResolverMatch:
        if not self.__current_resolver_match:
            self.__current_resolver_match = resolve(self.current_request.path_info)
        return self.__current_resolver_match

    def _is_filtered_by_content_type(self) -> bool:
        accepted_types = ('application/json', 'application/vnd.api+json')
        return self.current_response.get('content-type') not in accepted_types

    def _is_filtered_by_admin_namespace(self) -> bool:
        return self._resolver_match.namespace == 'admin'

    def _is_filtered_by_url_names_skipped(self) -> bool:
        return self._resolver_match.url_name in self.settings.SKIP_URL_NAME

    def is_filtered_by_namespaces_skipped(self) -> bool:
        return self._resolver_match.namespace in self.settings.SKIP_NAMESPACE

    def is_filtered_by_http_method(self) -> bool:
        return self.current_request.method not in self.settings.METHODS

    def is_filtered_by_status_code(self) -> bool:
        return self.current_response.status_code not in self.settings.STATUS_CODES
