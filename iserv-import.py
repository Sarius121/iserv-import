import pandas
import csv
import os
import re

# productive environment
DATA_SRC = "data-src/"
SCHILD_SUS_FILE = DATA_SRC + "sus2.csv"
GOMSTH_SUS_FILE = DATA_SRC + "GOMSTH.csv"
SCHILD_LUL_FILE = DATA_SRC + "LuL5.csv"
UNTIS_LUL_FILE = DATA_SRC + "GPU002.TXT"
CLASS_TEACHERS_FILE = DATA_SRC + "GPU003.TXT"

DATA_OUT = "data-out/"
ISERV_SUS_FILE = DATA_OUT + "Iserv SuS.csv"
ISERV_LUL_FILE = DATA_OUT + "Iserv LuL.csv"
GROUP_OWNERS_FILE = DATA_OUT + "group_owners.csv"

GOMSTH_MAX_COURSES = 12
VERBOSE = False
SUPPRESS_DUPLICATES = True

# map computed group names to correct group names (e.g. for downgraded LK groups to LK groups)
MANUAL_SEKII_COURSE_MAPPINGS = {"example_computed_course": "example_correct_course",
                                "example_computed_course2": "example_correct_course2"}

# groups which are not in UNTIS but shall still be imported
NOT_IN_UNTIS_EXCEPTIONS = ["example_not_in_untis_course", "example_not_int_untis_course2"]

# mappings from SchILD group names to UNTIS group names (the UNTIS names are taken in the end)
MANUAL_SEKI_MAPPINGS = {"example_schild_course": "example_untis_course",
                        "example_schild_course2": "example_untis_course2"}

# mapping from SchILD subject name to UNTIS subject name (only for searching in UNTIS, the SchILD name is taken in the end)
MANUAL_UNTIS_SEARCH_MAPPINGS = {"example_schild_subject": "example_untis_subject",
                                "example_schild_subject2": "example_untis_subject2"} 

MANUAL_TEACHER_COURSE_MAPPINGS = {}
MANUAL_USERNAME_MAPPINGS = {"example_username": "example_correct_username"}
MANUAL_TEACHER_NAME_MAPPINGS = {"example firstname": "example correct firstname"}
MANUAL_TEACHER_SURNAME_MAPPINGS = {"example lastname": "example correct lastname"}

CURRENT_DIR = os.path.dirname(__file__)

class Errors:

    def __init__(self):
        self.errors = []

    def add_error(self, type, student, short, message):
        self.errors.append({"type": type, "target": student, "short": short, "message": message})

    def __str__(self):
        output = "type\ttarget\tshort\n"
        for error in self.errors:
            if(SUPPRESS_DUPLICATES and error["short"] == "duplicate course detected"):
                continue
            output += error["type"] + "\t" + error["target"] + "\t" + error["short"] + "\n"
        return output

    def get_errors_verbose(self):
        output = "type\ttarget\tshort\tmessage\n"
        for error in self.errors:
            output += error["type"] + "\t" + error["target"] + "\t" + error["short"] + "\t" + error["message"] + "\n"
        return output

    def __len__(self):
        return len(self.errors)

def get_file(file):
    return os.path.join(CURRENT_DIR, file)

def is_SEKII(grade):
    return is_same_grade(grade, "EF") or is_same_grade(grade, "Q1") or is_same_grade(grade,"Q2")

def is_same_grade(grade1, grade2):
    grade1 = str(grade1)
    grade2 = str(grade2)
    if(grade1 == grade2):
        return True
    elif((grade1 == "10" and grade2 == "EF") or
        (grade1 == "EF" and grade2 == "10") or
        (grade1 == "11" and grade2 == "Q1") or
        (grade1 == "Q1" and grade2 == "11") or
        (grade1 == "12" and grade2 == "Q2") or
        (grade1 == "Q2" and grade2 == "12")):
        return True
    return False

def to_number_grade(grade):
    if(grade == "EF"):
        return "10"
    if(grade == "Q1"):
        return "11"
    if(grade == "Q2"):
        return "12"
    return grade

def to_string_grade(grade):
    if(grade == "10"):
        return "EF"
    if(grade == "11"):
        return "Q1"
    if(grade == "12"):
        return "Q2"
    return grade

def array_remove_empties(array):
    result = []
    for i in range(len(array)):
        if(len(array[i]) > 0):
            result.append(array[i])

    return result

def number_to_char(number):
    return chr(64 + int(number))

class Students:

    untis_cols = {"teacher": 5, "subject": 6, "course": 41}

    def __init__(self, schild_file, gomsth_file, untis_file, output_file, verbose=False):
        self.schild_file = schild_file
        self.gomsth_file = gomsth_file
        self.untis_file = untis_file
        self.output_file = output_file
        self.errors = Errors()
        # array with all groups for controlling purposes
        self.control_groups = []
        self.deleted_groups = []
        self.verbose = verbose

    # get the main firstname
    def __find_main_names(self, name):
        main_name = []
        while True:
            new_main_name = re.findall(r"(?:[^A-Z]+\s|^)([^a-z]+)(?:\s[^a-z]{0,1}[^A-Z]+|$)", name)
            if(len(new_main_name) == 0):
                if(len(main_name) == 0):
                    name = name
                else:
                    name = " ".join(main_name)
                names = name.split(" ")
                final_name = ""
                for i in range(len(names)):
                    part_names = names[i].split("-")
                    part_final_name = ""
                    for i2 in range(len(part_names)):
                        part_final_name += part_names[i2].capitalize() + "-"
                    final_name += part_final_name[:-1] + " "
                return final_name[:-1]
            if(len(new_main_name) > 1):
                self.errors.add_error("warning", students["Vorname"][i] + " " + students["Nachname"][i], "multiple main names", "student has multiple main names - concatenating all")
            main_name.append(new_main_name[0])
            name = name.replace(new_main_name[0], "")

    # get exchange groups for grades
    def __add_course_groups(self, groups, grade):
        if(isinstance(groups, float)):
            groups = ""
        if(len(groups) == 0):
            return groups + "Austausch " + grade
        else:
            return groups + ";Austausch " + grade

    # find given student in GOMSTH
    def __find_gomsth_student(self, student):
        try:
            # search by lastname
            matches = self.gomsth_data.loc[student["Nachname"]]
        except(KeyError):
            self.errors.add_error("warning", student["Vorname"] + " " + student["Nachname"], "no GOMSTH matches","student has no matches in GOMSTH")
            return None

        if(isinstance(matches, pandas.core.series.Series)):
            # single match -> already found
            return matches
        real_matches = []
        weak_matches = []
        for i in range(len(matches)):
            match = matches.iloc[i]
            # check for each match if it's the right firstname and grade
            if(match["RUFNAME"] == student["full_name"] and is_same_grade(match["KLASSE"], student["Klasse"])):
                real_matches.append(match)
            elif(match["RUFNAME"] == student["Vorname"] and is_same_grade(match["KLASSE"], student["Klasse"])):
                #sometimes the second name is not in GOMSTH
                weak_matches.append(match)

        if(len(real_matches) == 0 and len(weak_matches) > 0):
            # only take weak matches into account if there are no strong matches
            real_matches = weak_matches

        if(len(real_matches) != 1):
            # no matching students
            self.errors.add_error("error", student["Vorname"] + " " + student["Nachname"], str(len(real_matches)) + " matches","student has " + str(len(real_matches)) + " matches in GOMSTH")
            
        if(len(real_matches) > 0):
            # just return the first match if there are many
            return real_matches[0]
        else:
            return None

    # compute proper course name for a given course
    def __get_course_group_name(self, subject, number, teacher, grade):
        if(isinstance(number, float)):
            number = str(int(number))
        
        number = str(number)

        if(subject.lower() == "hb"):
            self.errors.add_error("warning", subject, "outsourced subject", "this subject is outsourced - don't create a group")
            return ""
        group = ""
        if(subject.upper() == subject):
            #LK
            group = subject.upper() + "_" + str(grade) + "_" + "LK" + number + "_" + teacher
        else:
            #GK
            group = subject.upper() + "_" + str(grade) + "_" + "GK" + number + "_" + teacher

        # map to other name if required
        if(group in MANUAL_SEKII_COURSE_MAPPINGS):
            group = MANUAL_SEKII_COURSE_MAPPINGS[group]

        return group

    # get GOMSTH groups for sekII students
    def __get_sekII_groups(self, student):
        gomsth_student = self.__find_gomsth_student(student)
        if(gomsth_student is None):
            return ""
        
        courses = ""
        for i in range(1, GOMSTH_MAX_COURSES + 1):
            try:
                if(pandas.isna(gomsth_student["FACH" + str(i)])):
                    #there are sometimes empty fields
                    continue
                course = self.__get_course_group_name(gomsth_student["FACH" + str(i)], gomsth_student["KURSNR" + str(i)], gomsth_student["FACHLEHRERKÜRZEL" + str(i)], gomsth_student["KLASSE"])
                if(len(course) > 0):
                    courses += course + ";"
            except KeyError:
                continue
        return courses[:-1]

    # add all groups to control groups
    def __add_control_groups(self, groups):
        for group in groups.split(";"):
            self.control_groups.append(group)

    # check if sekI group appears in UNTIS
    def __check_sekI_groups(self, grade, groups):
        edited_groups = ""
        for group in groups.split(";"):
            if(group.startswith("Fuellsel")):
                continue
            if(group.startswith("Austausch") or (group in NOT_IN_UNTIS_EXCEPTIONS)):
                # exchange groups and manual exceptions are just added
                edited_groups += group + ";"
            else:
                # manual mappings from SchILD style to UNTIS style
                if(group in MANUAL_SEKI_MAPPINGS):
                    group = MANUAL_SEKI_MAPPINGS[group]
                splitted_group = group.split(" ")
                subject = splitted_group[0]
                if(len(subject) > 2):
                    # unusually long subject
                    try:
                        # maybe there is a number at the end which is not important
                        number = int(subject[-1:])
                        subject = subject[:-1]
                    except ValueError:
                        pass

                # map for search
                if(subject in MANUAL_UNTIS_SEARCH_MAPPINGS):
                    subject = MANUAL_UNTIS_SEARCH_MAPPINGS[subject]

                # get all groups of the grade
                try:
                    matches = self.untis_data.loc[grade]
                except(KeyError):
                    self.errors.add_error("error", grade, "no UNTIS matches", "grade has no matches in UNTIS")
                    return ""

                if(isinstance(matches, pandas.core.series.Series)):
                    # handling single matches the same way as multi matches
                    matches = [matches]
                
                found = False
                for i in range(len(matches)):
                    if(isinstance(matches, list)):
                        match = matches[i]
                    else:
                        match = matches.iloc[i]

                    # compare subjects
                    if(match[self.untis_cols["subject"]] == subject):
                        edited_groups += group + ";"
                        found = True
                        break
                
                if(not found):
                    # log deleted groups for debugging purposes
                    self.deleted_groups.append(group)

        return edited_groups[:-1]
                    
    # main function for formatting students
    def format_students(self):
        print("Formating students ...")

        # rearrange columns
        print("Rearrange columns ...")
        self.schild_data = self.schild_data.reindex(columns=['Vorname','Nachname','Klasse','Import-ID','Gruppen'])

        print("Set main names and groups ...")
        total_students = len(self.schild_data)
        info_step = int(total_students / 10)
        formatted_students = 0
        # main loop for each student
        for i in range(len(self.schild_data)):
            # get main firstname
            full_name = self.schild_data["Vorname"][i]
            self.schild_data.loc[i, "Vorname"] = self.__find_main_names(self.schild_data["Vorname"][i])

            if(is_SEKII(self.schild_data["Klasse"][i])):
                # all SEKII groups in SchILD are wrong -> remove all SchILD groups and add GOMSTH groups
                self.schild_data.loc[i, "Gruppen"] = self.__get_sekII_groups({"Vorname": self.schild_data["Vorname"][i], "full_name": full_name, "Nachname": self.schild_data["Nachname"][i], "Klasse": self.schild_data["Klasse"][i]})
                
            # add exchange groups
            groups = self.__add_course_groups(self.schild_data["Gruppen"][i], self.schild_data["Klasse"][i])
            if(not is_SEKII(self.schild_data["Klasse"][i])):
                # check if all sekI groups are ok (against UNTIS and manual matches)
                groups = self.__check_sekI_groups(self.schild_data["Klasse"][i], groups)

            self.schild_data.loc[i, "Gruppen"] = groups

            # add control groups
            self.__add_control_groups(self.schild_data["Gruppen"][i])

            formatted_students += 1
            if((formatted_students % info_step) == 0):
                print(int(formatted_students / total_students * 100), "%")
        
        # some logs for debugging
        self.deleted_groups = list(set(self.deleted_groups))
        print("Deleted", len(self.deleted_groups), "groups because they weren't found in Untis:")
        output = ""
        for group in self.deleted_groups:
            output += group + "\t"
        print(output)

        print("Formatted students with", len(self.errors), "errors or warnings: ")
        if(self.verbose):
            print(self.errors.get_errors_verbose())
        else:
            print(self.errors)

    def __read_schild(self):
        print("Reading SCHILD_SUS file ...")
        self.schild_data = pandas.read_csv(self.schild_file, sep=";")
        print("Successfully read SCHILD_SUS file. Found ", len(self.schild_data), " students.")

    def __read_gomsth(self):
        print("Reading GOMSTH_SUS file ...")
        self.gomsth_data =  pandas.read_csv(self.gomsth_file, sep=",", index_col="FAMILIENNAME")
        print("Successfully read GOMSTH_SUS file. Found ", len(self.gomsth_data), " students.")

    def __read_untis(self):
        print("Reading UNTIS_SUS file ...")
        self.untis_data =  pandas.read_csv(self.untis_file, sep=",", index_col=4, header=None)
        print("Successfully read UNTIS_SUS file. Found ", len(self.untis_data), " teachers.")

    def read_data(self):
        self.__read_schild()
        self.__read_gomsth()
        self.__read_untis()

    def write_iserv(self):
        print("Writing ISERV_SUS file ...")
        self.schild_data.to_csv(self.output_file, sep=";", index=False, quoting=csv.QUOTE_NONNUMERIC)
        print("Successfully wrote ISERV_SUS file.")

    def get_control_groups(self):
        return list(set(self.control_groups))

class Teachers:
    untis_cols = {"grade": 4, "subject": 6, "course": 41}

    def __init__(self, schild_file, untis_file, class_teachers_file, output_file, group_owners_file, control_groups_students, verbose=False):
        self.schild_file = schild_file
        self.untis_file = untis_file
        self.class_teachers_file = class_teachers_file
        self.output_file = output_file
        self.group_owners_file = group_owners_file
        self.errors = Errors()
        self.control_groups = []
        self.control_groups_students = control_groups_students
        self.verbose = verbose
        self.group_owners = pandas.DataFrame(columns=["nutzer.name", "klasse"])
        self.deleted_groups = []

    def __add_control_groups(self, groups):
        for group in groups.split(";"):
            self.control_groups.append(group)

    def __get_teached_classes_in_grade(self, teacher, group, grade):
        subject = group.split(" ")[0]
        if(subject[:-1] in MANUAL_UNTIS_SEARCH_MAPPINGS):
            subject = MANUAL_UNTIS_SEARCH_MAPPINGS[subject[:-1]] # TODO this is very manual!

        try:
            matches = self.untis_data.loc[teacher]
        except(KeyError):
            return []

        if(isinstance(matches, pandas.core.series.Series)):
            matches = [matches]
        
        classes = []
        for i in range(len(matches)):
            if(isinstance(matches, list)):
                match = matches[i]
            else:
                match = matches.iloc[i]
            if(subject.startswith(match[self.untis_cols["subject"]]) and match[self.untis_cols["grade"]].startswith(grade)):
                classes.append(match[self.untis_cols["grade"]])

        if(len(classes) == 0):
            #if(recursive):
            #    self.errors.add_error("warning", group, "weak match in untis", "weak match (if found) in untis - you may want to check this")
            #    return self.__get_teached_classes_in_grade(teacher, subject[:-1], grade, False)
            #else:
            self.errors.add_error("error", group, "couldn't find involved classes", "couldn't find this course in Untis - adding all")
            classes.append(str(grade) + "a")
            classes.append(str(grade) + "b")
            classes.append(str(grade) + "c")

        return classes

    def __get_grade_groups(self, teacher, username, groups):
        grades = []
        for group in groups.split(";"):
            if(len(group) == 0):
                continue
            splitted_groups = group.split(" ")
            if(len(splitted_groups) == 1):
                group_grade = group.split("_")[1]
            else:
                group_grade = splitted_groups[1]

            try:
                group_grade = int(group_grade)
                if(group_grade < 10):
                    #print(group)
                    classes = self.__get_teached_classes_in_grade(teacher, group, str(group_grade))
                    #print(classes)
                    for class_s in classes:
                        grades.append(class_s)
                    #grades.append(str(group_grade) + "b")
                    #grades.append(str(group_grade) + "c")
                else:
                    grades.append(to_string_grade(str(group_grade)))
            except:
                if(group_grade == "11-12"):
                    grades.append(to_string_grade("11"))
                    grades.append(to_string_grade("12"))
                else:
                    grades.append(group_grade)


            # add teacher as group owner of this group
            self.__add_group(username, group)
        
        grades = list(set(grades)) # removing duplicates
        groups = ""
        for grade in grades:
            groups += "Austausch " + grade + ";"
            groups += "Lehrer " + grade + ";"


        # add class teacher groups
        if teacher in self.class_teachers_data:
            sections = {"o": False, "m":False, "u":False}
            for s_class in self.class_teachers_data[teacher]:
                if not is_SEKII(s_class["class"]):
                    groups += "Klasse " + s_class["class"] + ";"
                    if( int(s_class["class"][0]) <= 7):
                        sections["u"] = True
                    else:
                        sections["m"] = True
                else:
                    groups += "Jahrgang " + s_class["class"] + ";"
                    sections["o"] = True
                if s_class["type"] == 1:
                    if not is_SEKII(s_class["class"]):
                        self.__add_group(username, "Klasse " + s_class["class"])
                    else:
                        self.__add_group(username, "Jahrgang " + s_class["class"])
                    self.__add_group(username, "Austausch " + s_class["class"])
                    self.__add_group(username, "Lehrer " + s_class["class"])

            if sections["m"]:
                groups += "Klassenlehrer Mittelstufe;"
            if sections["u"]:
                groups += "Klassenlehrer Unterstufe;"
            if sections["o"]:
                groups += "Stufenleiter S II;"


        return groups[:-1]

    def __find_correct_course_name(self, names):
        for name in names:
            try:
                name = MANUAL_TEACHER_COURSE_MAPPINGS[name]
            except KeyError:
                pass
            if(self.__student_group_exists(name)):
                return name

        # return first one
        return names[0]

    def __add_group(self, username, group):
        group = group.lower().replace(" ", ".").replace("_", ".")
        self.group_owners.loc[len(self.group_owners)] = [username, group]
        return group

    def __get_untis_groups(self, teacher):
        try:
            matches = self.untis_data.loc[teacher]
        except(KeyError):
            self.errors.add_error("error", teacher, "no UNTIS matches", "teacher has no matches in UNTIS")
            return ""

        if(isinstance(matches, pandas.core.series.Series)):
            matches = [matches]
        
        courses = [] # store courses to detect duplicates
        pe_courses = []
        groups = ""
        for i in range(len(matches)):
            if(isinstance(matches, list)):
                match = matches[i]
            else:
                match = matches.iloc[i]

            # not SEKII courses should already have been extracted from schild
            if(is_SEKII(match[self.untis_cols["grade"]])):
                course = array_remove_empties(match[self.untis_cols["subject"]].split(" "))
                subject = course[0].upper() # all subjects should be in uppercase
                if(subject == "SPT"):
                    #self.errors.add_error("error", teacher, "SPT course cannot be handled", "SPT course is unknown")
                    # theoretical sport courses don't need a group
                    continue
                if (len(course) < 2):
                    self.errors.add_error("error", teacher, "no course number", "course " + str(course) + " has no number - ignoring")
                    continue
                number = course[1][1:]
                course_type = course[1][:1]
                grade = to_number_grade(match[self.untis_cols["grade"]])
                subject_number = -1
                try:
                    #remove numbers at the end of a subject
                    subject_number = int(subject[-1:])
                    subject = subject[:-1]
                except:
                    pass
                #print(number, "|", course_type, "|", subject)
                if(len(number) == 0 or len(course_type) == 0 or len(subject) == 0):
                    print("error")
                    self.errors.add_error("error", teacher, "empty course", "an empty course was detected and ignored: " + str(course))
                    continue

                course_id = teacher + "_" + subject + "_" + str(subject_number) + "_" + course_type + "_" + number + "_" + grade
                try:
                    courses.index(course_id)
                    # duplicate course
                    self.errors.add_error("warning", course_id, "duplicate course detected", "the course was detected multiple times in UNTIS file - only adding one time")
                    continue
                except:
                    courses.append(course_id)

                if(course_type == "L"):
                    group1 = subject + "_" + grade + "_" + "LK" + number + "_" + teacher
                    group2 = subject + "_" + grade + "_" + "LK" + number_to_char(number) + "_" + teacher
                    if(subject_number != -1):
                        group3 = subject + str(subject_number) + "_" + grade + "_" + "LK" + number + "_" + teacher
                        group4 = subject + str(subject_number) + "_" + grade + "_" + "LK" + number_to_char(number) + "_" + teacher
                        groups += self.__find_correct_course_name([group1, group2, group3, group4])
                    else:
                        groups += self.__find_correct_course_name([group1, group2])
                elif(course_type == "G"):
                    if(subject.lower() == "iv"):
                        subject = "VP-IP"
                    group = subject + "_" + grade + "_" + "GK" + number + "_" + teacher
                    if(subject_number != -1):
                        group2 = subject + str(subject_number) + "_" + grade + "_" + "GK" + number + "_" + teacher
                        groups += self.__find_correct_course_name([group, group2])
                    elif(subject.lower() == "sp"):
                        #different PE profiles
                        # one teacher may have multiple PE courses with different profiles and the numbers of the courses are different
                        possible_names = [group]
                        for i in range(1,4):
                            for i2 in range(1, int(number)+1):
                                group = subject + str(i) + "_" + grade + "_" + "GK" + str(i2) + "_" + teacher
                                try:
                                    pe_courses.index(group)
                                except ValueError:
                                    possible_names.append(group)
                        found_group = self.__find_correct_course_name(possible_names)
                        pe_courses.append(found_group)
                        groups += found_group
                    else:
                        groups += self.__find_correct_course_name([group])
                elif(course_type == "V"):
                    group = "V" + subject + "_" + grade + "_" + "GK" + number + "_" + teacher
                    if(subject_number != -1):
                        group2 = "V" + subject + str(subject_number) + "_" + grade + "_" + "GK" + number + "_" + teacher
                        groups += self.__find_correct_course_name([group, group2])
                    else:
                        groups += group
                elif(course_type == "Z"):
                    #ZKs don't have numbers (GE/SW)
                    if(subject.lower() == "ge"):
                        subject = "GN"
                    elif(subject.lower() == "sw"):
                        subject = "SN"
                    else:
                        self.errors.add_error("warning", course_id, "unknown ZK", "unknown ZK - handling it like normal GK")
                    groups += subject + "_" + grade + "_" + "GK" + number + "_" + teacher
                elif(course_type == "P"):
                    #PKs don't have numbers
                    groups += "P" + subject + "_" + grade + "_" + "GK" + number + "_" + teacher
                else:
                    self.errors.add_error("error", str(course), "unknown course type", "unknown course type " + course_type + " found")
                    continue

                groups += ";"
        return groups[:-1]

    def __student_group_exists(self, group):
        try:
            self.control_groups_students.index(group)
            return True
        except ValueError:
            return False

    def __check_sekI_groups(self, teacher, groups):
        edited_groups = ""
        if(len(groups) == 0):
            return ""
        for group in groups.split(";"):
            if(group.startswith("Fuellsel")):
                continue
            if(group in NOT_IN_UNTIS_EXCEPTIONS):
                edited_groups += group + ";"
                continue
            elif(group in MANUAL_SEKI_MAPPINGS):
                group = MANUAL_SEKI_MAPPINGS[group]
            splitted_group = group.split(" ")
            subject = splitted_group[0]
            grade = splitted_group[1]
            if(len(subject) > 2):
                #self.errors.add_error("warning", subject, "long subject detected", "long subject detected - searching without last digit")
                try:
                    number = int(subject[-1:])
                    subject = subject[:-1]
                except ValueError:
                    pass

            if(subject in MANUAL_UNTIS_SEARCH_MAPPINGS):
                    subject = MANUAL_UNTIS_SEARCH_MAPPINGS[subject]

            try:
                grade = str(int(grade))
            except ValueError:
                pass

            try:
                matches = self.untis_data.loc[teacher]
            except(KeyError):
                #self.errors.add_error("error", teacher, "no UNTIS matches", "teacher has no matches in UNTIS")
                # already logged
                self.deleted_groups.append(group)
                continue

            if(isinstance(matches, pandas.core.series.Series)):
                matches = [matches]
            
            found = False
            for i in range(len(matches)):
                if(isinstance(matches, list)):
                    match = matches[i]
                else:
                    match = matches.iloc[i]

                #if (subject.startswith("TWM")):
                #    print(match[self.untis_cols["subject"]])
                #    print(match[self.untis_cols["grade"]])
                if(subject.startswith(match[self.untis_cols["subject"]]) and match[self.untis_cols["grade"]].startswith(grade)):
                    edited_groups += group + ";"
                    found = True
                    break
            
            if(not found):
                self.deleted_groups.append(group)

        return edited_groups[:-1]

    def __check_control_groups(self, groups):
        if(len(groups) == 0):
            return
        for group in groups.split(";"):
            if(group.startswith("Lehrer") or group.startswith("Klasse") or group.startswith("Stufenleiter") or group.startswith("Jahrgang")):
                #these groups should only appear in teachers file ("Klasse" is added by IServ)
                continue
            if( not self.__student_group_exists(group)):
                self.errors.add_error("warning", group, "teachers only group", "group not found in students file")

    def format_teachers(self):
        print("Formating teachers ...")
        print("Rearrange columns ...")
        self.schild_data = self.schild_data.reindex(columns=['Vorname','Nachname','Information','ID','Gruppen'])

        print("Set groups ...")
        total_teachers = len(self.schild_data)
        info_step = int(total_teachers / 10)
        formatted_teachers = 0
        for i in range(len(self.schild_data)):
            groups = ""
            if(not pandas.isna(self.schild_data["Gruppen"][i])):
                groups = self.schild_data["Gruppen"][i]

            name = self.schild_data["Vorname"][i].split(" ")[0]
            if(name in MANUAL_TEACHER_NAME_MAPPINGS):
                name = MANUAL_TEACHER_NAME_MAPPINGS[name]
            self.schild_data.loc[i, "Vorname"] = name

            if(self.schild_data["Nachname"][i] in MANUAL_TEACHER_SURNAME_MAPPINGS):
                self.schild_data.loc[i, "Nachname"] = MANUAL_TEACHER_SURNAME_MAPPINGS[self.schild_data["Nachname"][i]]

            username = (self.schild_data["Vorname"][i] + "." + self.schild_data["Nachname"][i]).lower()
            replacements = [["ä","ae"], ["ö","oe"], ["ü","ue"], ["ß","ss"]]
            for replacement in replacements:
                username = username.replace(replacement[0], replacement[1])

            if(username in MANUAL_USERNAME_MAPPINGS):
                username = MANUAL_USERNAME_MAPPINGS[username]

            # check whether there is some unknown character left:
            for char in username:
                if not ((ord(char) >= 65 and ord(char) <= 90) or (ord(char) >= 97 and ord(char) <= 122) or (ord(char) >= 45 and ord(char) <= 46)):
                    self.errors.add_error("error", username, "wrong character found", "found the character '" + char + "' in username")

            # check whether all sekI groups are listed in untis
            groups = self.__check_sekI_groups(self.schild_data["Information"][i], groups)

            # add sekII course groups
            untis_groups = self.__get_untis_groups(self.schild_data["Information"][i])
            
            if(len(untis_groups) > 0):
                if(len(groups) > 0):
                    groups += ";" + untis_groups
                else:
                    groups = untis_groups

            # add "Austausch xy", "Lehrer xy" and "Klasse xy"
            grade_groups = self.__get_grade_groups(self.schild_data["Information"][i], username, groups)
            if(len(grade_groups) > 0):
                if(len(groups) > 0):
                    groups += ";" + grade_groups
                else:
                    groups = grade_groups

            self.schild_data.loc[i, "Gruppen"] = groups
            self.__add_control_groups(groups)
            self.__check_control_groups(groups)

            formatted_teachers += 1
            if((formatted_teachers % info_step) == 0):
                print(int(formatted_teachers / total_teachers * 100), "%")
        
        self.deleted_groups = list(set(self.deleted_groups))
        print("Deleted", len(self.deleted_groups), "groups because they weren't found in Untis:")
        output = ""
        for group in self.deleted_groups:
            output += group + "\t"
        print(output)

        print("Formatted teachers with", len(self.errors), "errors or warnings: ")
        if(self.verbose):
            print(self.errors.get_errors_verbose())
        else:
            print(self.errors)

    def __read_schild(self):
        print("Reading SCHILD_LUL file ...")
        self.schild_data = pandas.read_csv(self.schild_file, sep=";")
        print("Successfully read SCHILD_SUS file. Found ", len(self.schild_data), " teachers.")

    def __read_untis(self):
        print("Reading UNTIS_LUL file ...")
        self.untis_data =  pandas.read_csv(self.untis_file, sep=",", index_col=5, header=None)
        print("Successfully read GOMSTH_SUS file. Found ", len(self.untis_data), " teachers.")

    def __read_class_teachers(self):
        print("Reading CLASS_TEACHERS file ...")
        raw_class_teachers_data = pandas.read_csv(self.class_teachers_file, sep=",", header=None)
        self.class_teachers_data = {}
        for i in range(0, len(raw_class_teachers_data)):
            data = raw_class_teachers_data[1][i].split(" ")
            class_name = data[0]
            for j in range(1, len(data)):
                if not data[j] in self.class_teachers_data:
                    self.class_teachers_data[data[j]] = []
                self.class_teachers_data[data[j]].append({"class": class_name, "type": j })

        #print(self.class_teachers_data)
        print("Successfully read CLASS_TEACHERS file. Found ", len(self.class_teachers_data), " class teachers.")

    def read_data(self):
        self.__read_schild()
        self.__read_untis()
        self.__read_class_teachers()

    def write_iserv(self):
        print("Writing ISERV_LUL file ...")
        self.schild_data.to_csv(self.output_file, sep=";", index=False, quoting=csv.QUOTE_NONNUMERIC)
        print("Successfully wrote ISERV_LUL file.")

    def write_group_owners_file(self):
        print("Writing GROUP_OWNERS file ...")
        print("found", len(self.group_owners), "group owners")
        self.group_owners.to_csv(self.group_owners_file, sep=",", index=False)
        print("Successfully wrote GROUP_OWNERS file.")

    def get_control_groups(self):
        return list(set(self.control_groups))

def find_students_only_groups(teachers_groups, students_groups):
    print("found", len(teachers_groups), "teacher groups")
    for i in range(len(teachers_groups)):
        try:
            students_groups.remove(teachers_groups[i])
        except ValueError:
            continue
    print("Found", len(students_groups), "students only groups:")
    for i in range(len(students_groups)):
        print(students_groups[i])

def find_deletion_mismatches(teachers_groups, students_groups):
    print("found", len(teachers_groups), "deleted teachers groups")
    print("found", len(students_groups), "deleted students groups")
    matches = []
    for i in range(len(teachers_groups)):
        try:
            students_groups.remove(teachers_groups[i])
            matches.append(teachers_groups[i])
            teachers_groups[i] = ""
        except ValueError:
            continue
    print("Found", len(students_groups), "students only groups:")
    for i in range(len(students_groups)):
        print(students_groups[i])
    teachers_groups = list(set(teachers_groups))
    print("Found", len(teachers_groups), "teachers only groups:")
    for i in range(len(teachers_groups)):
        print(teachers_groups[i])
    print("Matches:")
    print(matches)

def Main():
    print("-----------------------")
    print("| IServ-Import-Helper |")
    print("-----------------------")
    print()
    print("### processing students ###")
    students = Students(get_file(SCHILD_SUS_FILE), get_file(GOMSTH_SUS_FILE), get_file(UNTIS_LUL_FILE), get_file(ISERV_SUS_FILE), VERBOSE)
    students.read_data()
    students.format_students()
    students.write_iserv()
    control_groups = students.get_control_groups()
    #control_groups = []
    print("----------------------------")
    print("### processing teachers ###")
    teachers = Teachers(get_file(SCHILD_LUL_FILE), get_file(UNTIS_LUL_FILE), get_file(CLASS_TEACHERS_FILE), get_file(ISERV_LUL_FILE), get_file(GROUP_OWNERS_FILE), control_groups, VERBOSE)
    teachers.read_data()
    teachers.format_teachers()
    teachers.write_iserv()
    teachers.write_group_owners_file()
    print("----------------------------")
    print("### checking results ###")
    find_students_only_groups(teachers.get_control_groups(), control_groups)
    find_deletion_mismatches(teachers.deleted_groups, students.deleted_groups)
    print("done")

if __name__ == "__main__":
    Main()