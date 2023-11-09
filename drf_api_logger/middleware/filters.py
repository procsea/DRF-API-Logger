from __future__ import annotations

from typing import TYPE_CHECKING
from collections import OrderedDict

from django.urls import resolve

if TYPE_CHECKING:
    from drf_api_logger.middleware.api_logger_middleware import APILoggerSettings
    from django.urls.resolvers import ResolverMatch

import logging

logger = logging.getLogger(__name__)
log_prefix = "######->>"


class APILogFilter:
    """This class is extendable as you can simply add a new method to validate... blabla
    If you want to add new filters, please do it here so they can be dynamically used depending on
    the user settings.

    Filter methods are "opt-in" depending on settings to avoid unecessary calls ... blabla
    """

    def __init__(self, settings: APILoggerSettings):
        self.settings = settings
        self.current_request = None
        self.current_response = None
        self.__current_resolver_match: ResolverMatch | None = None

        self.filter_methods = [
            # Default/Always ON filters
            "_is_filtered_by_content_type",
            "_is_filtered_by_admin_namespace"
        ]
        setting_conditioned_filters = OrderedDict(
            _is_filtered_by_url_names_skipped=self.settings.SKIP_URL_NAME,
            _is_filtered_by_namespaces_skipped=self.settings.SKIP_NAMESPACE,
            _is_filtered_by_http_method=self.settings.METHODS,
            _is_filtered_by_status_code=self.settings.STATUS_CODES,
        )

        for filter_method_name, setting in setting_conditioned_filters.items():
            if setting:
                self.filter_methods.append(filter_method_name)

    def is_filtered(self, request, response):
        self.current_request = request
        self.current_response = response
        try:
            for filter_method in self.filter_methods:
                if getattr(self, filter_method)():
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
        logger.info(f"{log_prefix} Filtering by: content_type")
        accepted_types = ('application/json', 'application/vnd.api+json')
        return self.current_response.get('content-type') not in accepted_types

    def _is_filtered_by_admin_namespace(self) -> bool:
        logger.info(f"{log_prefix} Filtering by: admin_namespace")
        return self._resolver_match.namespace == 'admin'

    def _is_filtered_by_url_names_skipped(self) -> bool:
        logger.info(f"{log_prefix} Filtering by: url_names_skipped")
        return self._resolver_match.url_name in self.settings.SKIP_URL_NAME

    def is_filtered_by_namespaces_skipped(self) -> bool:
        logger.info(f"{log_prefix} Filtering by: namespaces_skipped")
        return self._resolver_match.namespace in self.settings.SKIP_NAMESPACE

    def _is_filtered_by_http_method(self) -> bool:
        logger.info(f"{log_prefix} Filtering by: http_method")
        return self.current_request.method not in self.settings.METHODS

    def _is_filtered_by_status_code(self) -> bool:
        logger.info(f"{log_prefix} Filtering by: status_code")
        return self.current_response.status_code not in self.settings.STATUS_CODES
