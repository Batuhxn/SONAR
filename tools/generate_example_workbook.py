"""Recreate the synthetic Altium workbook from its committed CSV fixture."""
import csv
from pathlib import Path

from openpyxl import Workbook


def main():
    examples = Path(__file__).resolve().parents[1] / 'examples'
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'BoM'
    with (examples / 'altium_a1.csv').open(encoding='utf-8', newline='') as source:
        for row in csv.reader(source):
            worksheet.append(row)
    worksheet.freeze_panes = 'A2'
    worksheet.auto_filter.ref = worksheet.dimensions
    notes = workbook.create_sheet('About')
    notes.append(['Synthetic representative Altium export for SONAR A1 validation.'])
    notes.append(['Not an actual laboratory design or supplier quote.'])
    workbook.save(examples / 'altium_a1.xlsx')


if __name__ == '__main__':
    main()
