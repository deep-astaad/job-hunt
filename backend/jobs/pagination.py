from rest_framework.pagination import PageNumberPagination
from django.core.paginator import Paginator
from django.utils.functional import cached_property
from django.db import connection


class FastCountPaginator(Paginator):
    @cached_property
    def count(self):
        """
        Uses MySQL EXPLAIN to get an estimated row count for the query.
        If the estimate is > 1000, we skip the exact COUNT(*) to prevent
        massive performance hits on large InnoDB tables.
        If the estimate is small, we fallback to the exact count.
        """
        try:
            # Create a clone without ordering, as EXPLAIN with ORDER BY
            # can sometimes include filesort overhead in the estimate.
            query = self.object_list.query.clone()
            query.clear_ordering(True)
            compiler = query.get_compiler(using=self.object_list.db)
            sql, params = compiler.as_sql()

            with connection.cursor() as cursor:
                cursor.execute("EXPLAIN " + sql, params)
                row = cursor.fetchone()
                
                # Fetch columns to find where 'rows' is
                columns = [col[0].lower() for col in cursor.description]
                if "rows" in columns:
                    rows_idx = columns.index("rows")
                    estimate = int(row[rows_idx])
                    
                    # If it's a large table/result-set, return the estimate
                    if estimate > 1000:
                        return estimate
        except Exception:
            pass
        
        # Fallback to normal exact count
        return super().count


class FastPageNumberPagination(PageNumberPagination):
    """
    PageNumberPagination that uses a custom paginator to avoid
    slow exact COUNT(*) queries on large database tables.
    """
    django_paginator_class = FastCountPaginator
