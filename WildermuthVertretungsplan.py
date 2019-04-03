import requests
import subprocess
import csv
import re
import datetime


class WildermuthVertretungsplan:
    mUser = ''
    mPassword = ''
    mDate = ''
    mTable = []

    def __init__(self, user, password, pdf_file='Vertretungsplan.pdf', header_file='header.csv', body_file='body.csv'):
        self.mUser = user
        self.mPassword = password
        self.mPdfFile = pdf_file
        self.mHeaderFile = header_file
        self.mBodyFile = body_file
        self.fetchPDF()
        self.extractHeaderFromPDF()
        self.readDateFromHeader()
        self.extractTableFromPDF()
        self.readTableFromCSV()

    def getPdfFile(self):
        return self.mPdfFile

    def fetchPDF(self):
        with requests.Session() as s:
            # login to moodle
            r = s.post('https://moodle.wildermuth-gymnasium.de/moodle/blocks/exa2fa/login/',
                       data={'ajax': 'true', 'username': self.mUser, 'password': self.mPassword})

            if r.status_code != requests.codes.ok:
                print('moodle login failed:')
                r.raise_for_status()
                exit(1)

            # get PDF document
            r = s.get('https://moodle.wildermuth-gymnasium.de/moodle/pluginfile.php/494/mod_folder/content/0/Schueler-Vertretungsplan.pdf?forcedownload=1')
            if r.status_code != requests.codes.ok:
                print('get data failed:')
                r.raise_for_status()
                exit(1)

            # write PDF to file
            f = open(self.mPdfFile, 'wb')
            f.write(r.content)

    def extractHeaderFromPDF(self):
        # run tabula to extract header lines from PDF and store it to CSV
        # run tabula in stream mode to get header without lattice
        subprocess.run(['java', '-jar', 'tabula-1.0.2-jar-with-dependencies.jar', '-a', '%0,0,100,100', '-t', '-p', '1', '-o',
                        self.mHeaderFile, self.mPdfFile], check=True)

    def extractTableFromPDF(self):
        # run tabula to extract table from PDF and store it to CSV
        # run tabula in lattice mode to get full table
        subprocess.run(['java', '-jar', 'tabula-1.0.2-jar-with-dependencies.jar', '-a', '%0,0,100,100', '-l', '-p', 'all', '-o',
                        self.mBodyFile, self.mPdfFile], check=True)

    def readDateFromHeader(self):
        with open(self.mHeaderFile, newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                m = re.match('Klasse_moodle\\s+(\\d+)\\.(\\d+)\\.', row[0])
                if m:
                    # add missing year and return date of Vertretungsplan
                    self.mDate = datetime.date.today().replace(day=int(m.group(1)), month=int(m.group(2)))
                    return
        self.mDate = '???'

    def readTableFromCSV(self):
        with open(self.mBodyFile, newline='') as csvfile:
            reader = csv.reader(csvfile)

            isHeader = True
            self.mTable = []
            for row in reader:
                if row[0] == 'Klasse':
                    isHeader = False
                elif not isHeader:
                    self.mTable.append(row)

    def isSubscriptionMatching(self, row, subscription):
        for s in subscription:
            if s.lower() in row[0].lower():
                return True
        return False

    def getResult(self, subscription):
        entries = list(filter(lambda entry: self.isSubscriptionMatching(entry, subscription), self.mTable))
        return self.formatResult(entries)

    def formatResult(self, entries):
        s = '{}: '.format(self.mDate.strftime('%d.%m.%Y') if isinstance(self.mDate, datetime.date) else self.mDate)
        if len(entries) == 0:
            return s + "keine Einträge gefunden"
        else:
            s += '{} {} gefunden:'.format(len(entries), "Eintrag" if len(entries) == 1 else "Einträge")
            for e in entries:
                s += '\n' + e[0] + ': '
                if e[6].lower() == 'x':
                    s += '{}. Stunde {} *Entfall*'.format(e[1], e[5])
                else:
                    s += '{}. Stunde {} anstatt {} in Raum {} bei {}'.format(e[1], e[3], e[5], e[4], e[2])
                if e[7]:
                   s += ' ({})'.format(e[7])
            return s


if __name__ == '__main__':
    v = WildermuthVertretungsplan(user='user', password='password')
    print(v.getResult(['6c', '6D']))

