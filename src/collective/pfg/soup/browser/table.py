import json
from Acquisition import aq_parent
from Products.Five import BrowserView
from repoze.catalog.query import (
    Contains,
    Or,
)
from souper.soup import LazyRecord


class TableView(BrowserView):
    """datatables view
    """

    def columns(self):
        pfg = aq_parent(self.context)
        result = []
        for field in pfg._getFieldObjects():
            if not field.Schema()['pfgsoup_show'].get(field):
                continue
            if field.isLabel():
                continue
            result.append((field.fgField.widget.label,
                           field.fgField.getName(),
                           ))
        return result


class TableDataView(TableView):
    """datatables json data
    """

    def _extract_sort(self):
        sortparams = dict()
        columns = self.columns()
        # sortingcols and sortable are not used for now, but to be complete
        # it gets extracted
        sortparams['sortingcols'] = self.request.form.get('iSortingCols')
        sortparams['sortable'] = dict()
        sortparams['reverse'] = False
        sortcols_idx = 0
        sortparams['index'] = columns[sortcols_idx][1]
        sortparams['altindex'] = '_sort_%s' % sortparams['index']
        for idx in range(0, len(columns)):
            col = int(self.request.form.get('iSortCol_%d' % idx, 0))
            if col:
                sortcols_idx = idx
                sortparams['index'] = columns[idx][1]
            sabl = self.request.form.get('bSortable_%d' % sortcols_idx,
                                         'false')
            sortparams['sortable'][columns[idx][1]] = sabl == 'true'
        sdir = self.request.form.get('sSortDir_%d' % sortcols_idx, 'asc')
        sortparams['reverse'] = sdir == 'desc'
        return sortparams

    def _alldata(self, soup):
        data = soup.storage.data
        sort = self._extract_sort()
        try:
            iids = soup.catalog[sort['index']].sort(data.keys(),
                                                    reverse=sort['reverse'])
        except TypeError:
            if sort['altindex'] in soup.catalog:
                iids = soup.catalog[sort['altindex']].sort(data.keys(),
                                                       reverse=sort['reverse'])
            else:
                # must not happen, but keep as safety belt
                iids = data.keys()

        def lazyrecords():
            for iid in iids:
                yield LazyRecord(iid, soup)
        return soup.storage.length.value, lazyrecords()

    def _query(self, soup):
        from pprint import pprint
        pprint(self.request.form)
        columns = self.columns()
        querymap = dict()
        for idx in range(0, len(columns)):
            term = self.request.form['sSearch_%d' % idx]
            if not term or not term.strip():
                continue
            querymap[columns[idx][1]] = term
        global_term = self.request.form['sSearch']
        if not querymap and not global_term:
            return self._alldata(soup)
        query = None
        if querymap:
            for index_name in querymap:
                query_element = Contains(index_name, querymap[index_name])
                if query is not None:
                    query &= query_element
                else:
                    query = query_element

        global_query = None
        if global_term:
            for index_name in soup.catalog:
                query_element = Contains(index_name, global_term)
                if global_query is not None:
                    global_query = Or(global_query, query_element)
                else:
                    global_query = query_element
        if query is not None and global_query is not None:
            query = Or(query, global_query)
        elif query is None and global_query is not None:
            query = global_query
        query.print_tree()
        sort = self._extract_sort()
        try:
            result = soup.lazy(query, sort_index=sort['index'],
                               reverse=sort['reverse'],
                               with_size=True)
        except TypeError:
            result = soup.lazy(query, sort_index=sort['altindex'],
                               reverse=sort['reverse'],
                               with_size=True)

        length = result.next()
        return length, result

    def _slice(self, fullresult):
        start = int(self.request.form['iDisplayStart'])
        length = int(self.request.form['iDisplayLength'])
        count = 0
        for lr in fullresult:
            if count >= start and count < (start + length):
                yield lr
            if count >= (start + length):
                break
            count += 1

    def __call__(self):
        soup = self.context.get_soup()
        aaData = list()
        length, lazydata = self._query(soup)
        colnames = [_[1] for _ in self.columns()]

        def record2list(record):
            result = list()
            for colname in colnames:
                result.append(record.attrs.get(colname, ''))
            return result
        for lazyrecord in self._slice(lazydata):
            aaData.append(record2list(lazyrecord()))
        data = {
          "sEcho": int(self.request.form['sEcho']),
          "iTotalRecords": soup.storage.length.value,
          "iTotalDisplayRecords": length,
          "aaData": aaData,
        }
        return json.dumps(data)
