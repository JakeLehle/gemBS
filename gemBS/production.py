#!/usr/bin/env python
"""Production pipelines"""
import os
import re
import fnmatch
import logging
import json
import sys
import time
import datetime
from sys import exit
import subprocess
import threading as th

from .utils import Command, CommandException, try_get_exclusive
from .reportStats import LaneStats,SampleStats
from .report import buildReport as htmlBuildReport
from .sphinx import buildReport as sphinxBuildReport
from .bsCallReports import *
from .__init__ import *


class BasicPipeline(Command):
    """General mapping pipeline class."""

    gemBS_json = None

    def __init__(self):
        # general parameters
        self.command = None 
        self.time = str(datetime.datetime.now())
        self.threads = 1
        self.membersInitiation()
        
    def membersInitiation(self):
        #To fullfill in the child class
        pass
        
    def log_parameter(self):
        """Print selected parameters"""
        if self.command != None:
            printer = logging.gemBS.gt
      
            printer("")
            printer("Command {} started at {}".format(self.command, self.time))
            printer("")
       
        self.extra_log()
        
    def extra_log(self):
        """Extra Parameters to be printed"""
        #Virtual methos, to be define in child class
        pass


class PrepareConfiguration(Command):
    title = "Prepare"
    description = """Sets up pipeline directories and controls files.
                      
Input Files:

  Two files are required, a configuration file describing the model parameters and analysis directory
  structure, and second file describing the sample metadata and associated data files.

  The sample file will normally be a text file in CSV format with a  header line,
  although there is also the option to import a JSON file from the CNAG LIMS.

  A full description of the input file formats can be found in the gemBS documentation.  

  The prepare command reads in the configuration files and writes a JSON file with the data from both
  files, that is used by the subsequent gemBS commands.  Any parameters supplied in the configuration
  files is used as the default by the other gemBS commands, so judicious use can prevent a lot of typing
  and help standardize analyses.  

  The prepare command will then check that the mimum required information has been provided, and will check 
  for the existence of key input files (notable the genome reference fasta file).  

  A persistant (disk-based) sqlite3 database is used by default so that gemBS can track at what stage the pipeline
  has reached and handle pipeline steps that failed.  This allows normal operation and restarting of the pipeline 
  to be achieved using minimal input from the user.  

  The use of the disk-base database is recommended for normal operations but does require a shared filesystem (that 
  supports non-local file locks) across all instances of gemBS that are running on the same datafiles.  If this is 
  not the case then this can be turned off using the --no-db option.  Use of this option will require that the user 
  tracks the state of the analysis themselves.  Note that if multiple instances of gemBS are run simultaneously on
  common analysis directories (i.e., using a shared filesystem, stroing output files in the same locations) then the
  disk based database must be used to avoid interference between the different gemBS instances.

  By default the database (if used) is stored in the file .gemBS/gemBS.db and the output JSON file is stored in 
  .gemBS/gemBS.json.  If the -no-db option is set then the JSON file will be stored to the file gemBS.json in the
  current directory.  The --output option can be used to specify an alternate locationn for the JSON file and the 
  --db-file option can specify an alternate locaiton for the database file.  The database location is stored in the
  JSON file so that it can be recovered by subsequent calls to gemBS.  However if the default location is not used 
  for the JSON file them it will be necessary to specify the location of the JSON file for each gemBS command.  It 
  is therefore advised to stay with the default option if possible.

"""
                
    def register(self, parser):
        ## required parameters
        parser.add_argument('-c', '--config', dest="config", help="""Text config file with gemBS parameters.""",required=True)
        parser.add_argument('-t', '--text-metadata', dest="text_metadata", help="Sample metadata in csv file.  See documentation for description of file format.")
        parser.add_argument('-o', '--output', dest="output", help="Output JSON file.  See documentation for description of file format.")
        parser.add_argument('-D', '--no-db', dest="no_db", action="store_true", help="Do not use disk base database.")
        parser.add_argument('-d', '--db-file', dest="dbfile", help="Specify location for database file.")
        parser.add_argument('-l', '--lims-cnag-json', dest="lims_cnag_json", help="Lims CNAG subproject JSON file.")
        
    def run(self,args):
        #Try text metadata file
        if args.text_metadata is not None:
            if os.path.isfile(args.text_metadata):
                prepareConfiguration(text_metadata=args.text_metadata,configFile=args.config,no_db=args.no_db,dbfile=args.dbfile,output=args.output)
            else:
                raise CommandException("File %s not found" %(args.text_metadata))
        elif args.lims_cnag_json is not None:
            if os.path.isfile(args.lims_cnag_json):
                prepareConfiguration(lims_cnag_json=args.lims_cnag_json,configFile=args.config,no_db=args.no_db,dbfile=args.dbfile,output=args.output)
            else:
                raise CommandException("File %s not found" %(args.lims_cnag_json))
        else:
            raise CommandException("No input file provided")
                    
     
class Index(BasicPipeline):
    title = "Index genomes"
    description = """Reference indexing for Bisulfite GEM mapping 

  Generates by default a file called reference.BS.gem (GEM Index), reference.BS.info (Information about the index process) and
  reference.chrom.sizes (a list of contigs and sizes).  Optionally the index command will also take a list of bed files with SNP names 
  and locations (such as can be downloaded from dbSNP) and make an indexed file that can be used during the calling process to add SNP 
  names into the output VCF/BCF file.  The list of input files for thed dbSNP index generation can include shell wildcards (*, ? etc.)

  PLEASE NOTE!  If bisulfite conversion control sequences have been added to the sequencing libraries then their sequences should be 
  added to the fasta reference file, and gemBS should be told the names of these sequences.

  More details about the reference files, conversion control sequences, GEM index and dbSNP index can be found in the gemBS documentation.

    """

    def register(self, parser):
        ## required parameters
        parser.add_argument('-t', '--threads', dest="threads", help='Number of threads. By default GEM indexer will use the maximum available on the system.',default=None)
        parser.add_argument('-s', '--sampling-rate', dest="sampling_rate", help='Text sampling rate.  Increasing will decrease index size at the expense of slower  performance.',default=None)
        parser.add_argument('-p', '--populate-cache', dest="populate_cache", help='Populate reference cache if required (for CRAM).',action="store_true",required=False,default=None)
        parser.add_argument('-d', '--list-dbSNP-files',dest="list_dbSNP_files",nargs="+",metavar="FILES",
                            help="List of dbSNP files (can be compressed) to create an index to later use it at the bscall step. The bed files should have the name of the SNP in column 4.",default=[])

    def run(self, args):
        self.command = 'index'
        jsonData = JSONdata(Index.gemBS_json)
        args.list_dbSNP_files = jsonData.check(section='index',key='dbsnp_files',arg=args.list_dbSNP_files,list_type=True,default=[])
        db = database(jsonData)
        db.check_index()
        c = db.cursor()
        db_data = {}
        for fname, ftype, status in c.execute("SELECT * FROM indexing"):
            db_data[ftype] = (fname, status)

        fasta_input, fasta_input_ok = db_data['reference']
        extra_fasta_files = jsonData.check(section='index',key='extra_references',arg=None,list_type=True,default=[])
        populate_cache = jsonData.check(section='index',key='populate_cache',arg=args.populate_cache, boolean=True)
        index_name, index_ok = db_data['index']
        nonbs_index_name, nonbs_index_ok = db_data.get('nonbs_index',(None, 0))
        csizes, csizes_ok = db_data['contig_sizes']
        greference, greference_ok = db_data['gembs_reference']
        contig_md5, contig_md5_ok = db_data['contig_md5']

        # We trigger a regeneration of the contig_md5 file if we want to check/populate the cache
        if populate_cache:
            contig_md5_ok = False
        dbsnp_index, dbsnp_ok = db_data.get('dbsnp_idx',(None, 0))
        self.threads = jsonData.check(section='index',key='threads',arg=args.threads)
        args.sampling_rate = jsonData.check(section='index',key='sampling_rate',arg=args.sampling_rate)
        args.list_dbSNP_files = jsonData.check(section='index',key='dbsnp_files',arg=args.list_dbSNP_files,list_type=True,default=[])
        if not fasta_input: raise ValueError('No input reference file specified for Index command')
        if extra_fasta_files == []:
            extra_fasta_files = None
        if greference_ok == 1:
            logging.warning("gemBS reference {} already exists, skipping creation".format(greference))
        else:
            ret = mk_gembs_reference(fasta_input, greference, contig_md5, extra_fasta_files=extra_fasta_files, threads=self.threads, populate_cache=populate_cache)
            if ret:
                self.command = 'mk_gembs_reference'
                self.log_parameter()
                
                logging.gemBS.gt("gemBS reference done: {}".format(greference))
                db.check_index()
                if contig_md5 != None:
                    logging.gemBS.gt("Contig md5 file created: {}".format(contig_md5))
                    contig_md5_ok = True
        
        if index_ok == 1:
            logging.warning("Bisulphite Index {} already exists, skipping indexing".format(index_name))
        else:
            self.command = 'index'
            self.log_parameter()
            ret = index(index_name, greference, threads=self.threads, sampling_rate=args.sampling_rate, tmpDir=os.path.dirname(index_name))
            if os.path.exists(csizes):
                os.remove(csizes)
                csizes_ok = 0
            if ret:
                logging.gemBS.gt("Index done: {}".format(index))

        if nonbs_index_name != None:
            if nonbs_index_ok == 1:
                logging.warning("Non-bisulphite Index {} already exists, skipping indexing".format(nonbs_index_name))
            else:
                self.command = 'nonbs index'
                self.log_parameter()
                ret = index(nonbs_index_name, greference, nonbs_flag=True, threads=self.threads, sampling_rate=args.sampling_rate, tmpDir=os.path.dirname(index_name))
                if ret:
                    logging.gemBS.gt("Non-bisulfite index done: {}".format(index))
        if not contig_md5_ok:
            ret = mk_contig_md5(contig_md5, greference, populate_cache)
            if ret:
                logging.gemBS.gt("Contig md5 file created: {}".format(contig_md5))
        if dbsnp_index != None:
            if dbsnp_ok:
                logging.warning("dbSNP Index {} already exists, skipping indexing".format(dbsnp_index))
            else:
                if args.list_dbSNP_files:
                    ret = dbSNP_index(list_dbSNP_files=args.list_dbSNP_files,dbsnp_index=dbsnp_index)
                    if ret:
                        logging.gemBS.gt("dbSNP index done: {}".format(ret))
                else:
                    raise CommandException("No input files for dbSNP index must be specified using the -d option or the dbsnp_files configuration key.")
        elif args.list_dbSNP_files:
            raise CommandException("The dbSNP Index file must be specified using the configuration parameter dbSNP_index.")

        if csizes_ok == 1:
            logging.warning("Contig sizes file {} already exists, skipping indexing".format(csizes))
        else:
            config = jsonData.config
            omit = config['calling'].get('omit_contigs', [])
            ret = makeChromSizes(index_name, csizes, omit)
            if ret:
                logging.gemBS.gt("Contig sizes file done: {}".format(ret))
                db.check()
                jdict = jsonData.jsconfig
                jdict['contigs'] = jsonData.contigs
                with open(Index.gemBS_json, 'w') as of:
                    json.dump(jdict, of, indent=2)
                
       
class Mapping(BasicPipeline):
    title = "Bisulphite mapping"
    description = """Maps single end or paired end bisulfite sequence using the GEM3 mapper. 
  
  By default the map command will try and perform mapping on all datafiles that it knows about that have not already been mapped.
  If all datafiles for a sample have been mapped then the map command will merge the BAM files if multiple BAMs exist for the sample.
  The resulting BAM will then be indexed and the md5 sum calculated. If the option --remove is set or 'remove_individual_bams' is set 
  to True in the  configuration file then the individual BAM files will be deleted after the merge step has been successfully completed. 
  The --no-merge options will prevent this automatic merging - this can be useful for batch processing.

  Aside from the --no-merge option, if no disk based database is being used for gemBS and separate instances of gemBS are being run on 
  non-shared file systems then the merging will not always be performed automatically.  When the merging is not performed automatically
  for whatever reason, it can be invoked manually using the merge-bams command.

  The mapping process can be restricted to a single sample using the option '-n <SAMPLE NAME>' or '-b <SAMPLE BARCODE>'.  The mapping can 
  also be restricted to a single dataset ID using the option '-D <DATASET>'

  The locations of the input and output data are given by the configuration files; see the gemBS documentation for details.

  The --dry-run option will output a list of the mapping / merging operations that would be run by the map command without executing
  any of the commands.  The --json <JSON OUTPUT> options is similar to --dry-run, but writes the commands to be executed in JSON
  format to the supplied output file, including information about the input and output files for the commands.  The --ignore-db option
  modifies the --dry-run and --json options such that the database is not consulted (i.e., gemBS assumes that nothing has already
  been completed.

    """   
 
    def register(self,parser):
        ## required parameters
        parser.add_argument('-D', '--dataset', dest="fli", metavar="DATASET", help='Dataset to be mapped.', required=False)
        parser.add_argument('-n', '--sample-name', dest="sample_name", metavar="SAMPLE", help='Name of sample to be mapped.', required=False)
        parser.add_argument('-b', '--barcode', dest="sample", metavar="BARCODE", help='Barcode of sample to be mapped.', required=False)
        parser.add_argument('-d', '--tmp-dir', dest="tmp_dir", metavar="PATH", help='Temporary folder to perform sorting operations. Default: /tmp')      
        parser.add_argument('-t', '--threads', dest="threads", help='Number of threads for the mapping pipeline. Default: 1');
        parser.add_argument('--map-threads', dest="map_threads", help='Number of threads for GEM mapper. Default: threads',default=None)
        parser.add_argument('--sort-threads', dest="sort_threads", help='Number of threads for the sort operations. Default: threads',default=None)
        parser.add_argument('--merge-threads', dest="merge_threads", help='Number of threads for the merge operations. Default: threads',default=None)
        parser.add_argument('--sort-memory', dest="sort_memory", help='Per thread memory used for the sort operation. Default: 768M',default=None)
        parser.add_argument('-T', '--type', dest="ftype", help='Type of data file (PAIRED, SINGLE, INTERLEAVED, STREAM, BAM)')
        parser.add_argument('-p', '--paired-end', dest="paired_end", action="store_true", help="Input data is Paired End")
        parser.add_argument('-r', '--remove', dest="remove", action="store_true", help='Remove individual BAM files after merging.', required=False)
        parser.add_argument('-R', '--reverse-conversion', dest="reverse_conv", action="store_true", help='Perform G2A conversion on read 1 and C2T on read 2 rather than the reverse.', required=False)
        parser.add_argument('-s', '--read-non-stranded', dest="read_non_stranded", action="store_true", 
                              help='Automatically selects the proper C->T and G->A read conversions based on the level of Cs and Gs on the read.')     
        parser.add_argument('-u', '--underconversion-sequence', dest="underconversion_sequence", metavar="SEQUENCE", help='Name of unmethylated sequencing control.', default=None,required=False)
        parser.add_argument('-v', '--overconversion-sequence', dest="overconversion_sequence", metavar="SEQUENCE", help='Name of methylated sequencing control.', default=None,required=False)
        parser.add_argument('--non-bs', dest="non_bs", action="store_true", help="Use regular (non bisulfite) index")
        parser.add_argument('--no-merge', dest="no_merge", action="store_true", help="Do not automatically merge BAMs")
        parser.add_argument('--dry-run', dest="dry_run", action="store_true", help="Output mapping commands without execution")
        parser.add_argument('--json', dest="dry_run_json",metavar="JSON FILE",help="Output JSON file with details of pending commands")
        parser.add_argument('--ignore-db', dest="ignore_db", action="store_true",help="Ignore database for --dry-run and --json commands")
        parser.add_argument('--benchmark-mode', dest="benchmark_mode", action="store_true",help="Omit dates etc. to make file comparison simpler", required=False)
                    
    def run(self, args):     
        self.all_types = ['PAIRED', 'INTERLEAVED', 'SINGLE', 'BAM', 'SAM', 'STREAM', 'PAIRED_STREAM', 'SINGLE_STREAM', 'COMMAND', 'SINGLE_COMMAND', 'PAIRED_COMMAND']
        self.paired_types = ['PAIRED', 'INTERLEAVED', 'PAIRED_STREAM', 'PAIRED_COMMAND']
        self.stream_types = ['STREAM', 'SINGLE_STREAM', 'PAIRED_STREAM']
        self.command_types = ['COMMAND', 'SINGLE_COMMAND', 'PAIRED_COMMAND']

        self.args = args
        self.ftype = args.ftype
        self.paired_end = args.paired_end
        if self.ftype:
            self.ftype = self.ftype.upper()
            if self.ftype in self.all_types:
                if self.ftype == 'STREAM': 
                    self.ftype = 'PAIRED_STREAM' if self.paired_end else 'SINGLE_STREAM'
                elif self.ftype in self.paired_types:
                    self.paired_end = True
                elif self.paired_end:
                    raise ValueError('Type {} is not paired'.format(self.ftype))
            else:
                raise ValueError('Invalid type specified {}'.format(self.ftype))
        self.dry_run = args.dry_run
        self.dry_run_json = args.dry_run_json
        self.no_merge = args.no_merge
        self.non_bs = args.non_bs
                      
        if self.dry_run or self.dry_run_json:
            self.ignore_db = args.ignore_db
        else:
            self.ignore_db = False
            
        if self.dry_run_json:
            self.json_commands = {}
        self.command = 'map'
        # JSON data
        self.jsonData = JSONdata(Mapping.gemBS_json)

        sdata = self.jsonData.sampleData
        if args.fli != None:
            args.sample = sdata[args.fli].sample_barcode

        if not args.sample and args.sample_name:
            for k, v in sdata.items():
                if v.sample_name == args.sample_name:
                    args.sample = v.sample_barcode
                    break
            else:
                raise ValueError("Sample name '{}' not found".format(args.sample_name))
            
        self.name = args.sample
        
        self.tmp_dir = self.jsonData.check(section='mapping',key='tmp_dir',arg=args.tmp_dir,dir_type=True)
        self.threads = self.jsonData.check(section='mapping',key='threads',arg=args.threads,default='1')
        self.map_threads = self.jsonData.check(section='mapping',key='map_threads',arg=args.map_threads,default=self.threads)
        self.sort_threads = self.jsonData.check(section='mapping',key='sort_threads',arg=args.sort_threads,default=self.threads)
        self.merge_threads = self.jsonData.check(section='mapping',key='merge_threads',arg=args.merge_threads,default=self.threads)
        self.sort_memory = self.jsonData.check(section='mapping',key='sort_memory',arg=args.sort_memory, default='768M')
        self.reverse_conv = self.jsonData.check(section='mapping',key='reverse_conversion',arg=args.reverse_conv, boolean=True)
        self.benchmark_mode = self.jsonData.check(section='mapping',key='benchmark_mode',arg=args.benchmark_mode, boolean=True)
        self.read_non_stranded = self.jsonData.check(section='mapping',key='non_stranded',arg=args.read_non_stranded, boolean=True)
        if self.read_non_stranded:
            self.reverse_conv = False
        self.remove = self.jsonData.check(section='mapping',key='remove_individual_bams',arg=args.remove, boolean=True)
        self.underconversion_sequence = self.jsonData.check(section='mapping',key='underconversion_sequence',arg=args.underconversion_sequence)
        self.overconversion_sequence = self.jsonData.check(section='mapping',key='overconversion_sequence',arg=args.overconversion_sequence)

        self.input_dir = self.jsonData.check(section='mapping',key='sequence_dir',arg=None,default='.',dir_type=True)
        self.db = database(self.jsonData)
        self.db.check_index()
        self.mem_db = self.db.mem_db()

        # If we are doing a dry-run we will use an in memory copy of the db so the on disk db is not touched
        if self.dry_run or self.dry_run_json:
            self.db.copy_to_mem()

        self.index_status = {}
        c = self.db.cursor()
        for ix_type in ('index', 'nonbs_index'):
            c.execute("SELECT file, status FROM indexing WHERE type = '{}'".format(ix_type))
            self.index_status[ix_type] = c.fetchone()
        for fname, ftype, status in c.execute("SELECT * FROM indexing"):
            if ftype == 'contig_md5':
                if status != 1:
                    raise CommandException("contig md5 file {} not found.  Run 'gemBS index' or correct configuration file and rerun".format(fname))
                else:                
                    self.contig_md5 = fname;
            elif ftype == 'gembs_reference':
                if status != 1:
                    raise CommandException("gemBS reference {} not found.  Run 'gemBS index' or correct configuration file and rerun".format(fname))
                else:
                    self.fasta_reference = fname            
        
        #Check Temp Directory
        if self.tmp_dir and not os.path.isdir(self.tmp_dir):
            raise CommandException("Temporary directory %s does not exists or is not a directory." %(self.tmp_dir))

        if args.sample:
            ret = c.execute("SELECT * from mapping WHERE sample = ?", (args.sample,))
        else:
            ret = c.execute("SELECT * from mapping")
        work_list = {}
        for fname, fl, smp, ftype, status in ret:
            if self.ignore_db:
                status = 0
            if not smp in work_list:
                work_list[smp] = [None, []]
            if ftype == 'MRG_BAM':
                if status == 0:
                    work_list[smp][0] = fname
            else:
                work_list[smp][1].append((fl, fname, ftype, status))
        for smp, v in work_list.items():
            bamlist = []
            skipped = False
            for fl, fname, ftype, status in v[1]:
                if status == 0:
                    if args.fli != None and args.fli != fl:
                        skipped = True
                    else:
                        self.do_mapping(fl)
                if ftype != 'SINGLE_BAM':
                    bamlist.append(fname)
            if not skipped and v[0] != None and not self.no_merge:                    
                self.do_merge(smp, bamlist, v[0])
                    
        if self.dry_run_json and self.json_commands:
            with open(self.dry_run_json, 'w') as of:
                json.dump(self.json_commands, of, indent = 2)
            
    def do_mapping(self, fli):
        # Check if FLI still has status 0 (i.e. has not been claimed by another process)
        self.db.isolation_level = None
        c = self.db.cursor()

        try_get_exclusive(c)
        if self.ignore_db:
            c.execute("SELECT * FROM mapping WHERE fileid = ?", (fli,))
        else:
            c.execute("SELECT * FROM mapping WHERE fileid = ? AND status = 0", (fli,))
        ret = c.fetchone()
        if ret:
            # Claim FLI by setting status to 3
            outfile, fl, smp, filetype, status = ret
            c.execute("UPDATE mapping SET status = 3 WHERE filepath = ?", (outfile,))
            c.execute("COMMIT")
            self.name = smp
            # Register output files and db cleanup in case of failure
            odir = os.path.dirname(outfile)
            jfile = os.path.join(odir, fl + '.json')
            ixfile = os.path.join(odir, smp + '.bai')
            database.reg_db_com(outfile, "UPDATE mapping SET status = 0 WHERE filepath = '{}'".format(outfile), [outfile, jfile, ixfile])                

            try:
                fliInfo = self.jsonData.sampleData[fli] 
            except KeyError:
                raise ValueError('Data file {} not found in config file'.format(fli))

            sample = fliInfo.sample_name
            bc = fliInfo.sample_barcode
            bis = fliInfo.bisulfite
            if self.non_bs: bis = False
            ix_type = 'index' if bis else 'nonbs_index'
            v = self.index_status[ix_type]
            if v != None:
                self.index = v[0]
                if v[1] != 1:
                    raise CommandException("GEM Index {} not found.  Run 'gemBS index' or correct configuration file and rerun".format(self.index))
            else:
                raise CommandException("GEM {} not found.  Run 'gemBS index' or correct configuration file and rerun".format(six_type))
                
            input_dir = self.input_dir.replace('@BARCODE',bc).replace('@SAMPLE',sample)

            #Paired
            self.paired = self.paired_end
            ftype = self.ftype
            if not self.paired:
                if ftype == None: ftype = fliInfo.type 
                if ftype in self.paired_types: self.paired = True

            inputFiles = []
        
            # Find input files
            if not ftype:
                ftype = fliInfo.type
            if not ftype in self.stream_types:
                files = fliInfo.file
                if files:            
                    # If filenames were specified in configuration file then use them
                    if ftype == 'PAIRED':
                        if not (files.get('1') and files.get('2')):
                            ftype = 'INTERLEAVED'
                    if ftype == 'PAIRED':
                        f1 = files['1']
                        f2 = files['2']
                        if not f1.endswith('|'):
                            f1 = os.path.join(input_dir,f1)
                        if not f2.endswith('|'):
                            f2 = os.path.join(input_dir,f2)
                        inputFiles = [f1, f2]
                    else:
                        for k,v in files.items():
                            if ftype is None:
                                if 'bam' in v: 
                                    ftype = 'BAM'
                                elif 'sam' in v:
                                    ftype = 'SAM'
                                else:
                                    ftype = 'INTERLEAVED' if self.paired else 'SINGLE'
                            if ftype in self.command_types:
                                inputFiles.append(v)
                            else:
                                inputFiles.append(os.path.join(input_dir,v))
                                
                            break
                else:
                    # Otherwise search in input directory for possible data files
                    if not os.path.isdir(input_dir):
                        raise ValueError("Input directory {} does not exist".format(input_dir))

                    # Look for likely data files in input_dir
                    for fli in (fliInfo.getFli(),fliInfo.alt_fli):
                        if fli == None:
                            continue
                        reg = re.compile("(.*){}(.*?)([12])?[.](fastq|fq|fasta|fa|bam|sam)([.][^.]+)?$".format(fli, re.I))
                        mlist = []
                        for file in os.listdir(input_dir):
                            m = reg.match(file)
                            if m: 
                                if m.group(5) in [None, '.gz', '.xz', 'bz2', 'z']:
                                    if ftype == 'PAIRED' and (m.group(3) not in ['1', '2'] or m.group(4).lower() not in ['fasta', 'fa', 'fastq', 'fq']): continue
                                    if ftype in ['SAM', 'BAM'] and m.group(4).lower() not in ['sam', 'bam']: continue
                                    mlist.append((file, m))
                            
                        if len(mlist) == 1:
                            (file, m) = mlist[0]
                            skip = False
                            if ftype is None:
                                if m.group(4).lower() in ['SAM', 'BAM']:
                                    ftype = 'BAM' if m.group(4).lower == 'BAM' else 'SAM'
                                else:
                                    ftype = 'INTERLEAVED' if self.paired else 'SINGLE'
                            elif ftype == 'PAIRED' or (ftype == 'SAM' and m.group(4).lower != 'sam') or (ftype == 'BAM' and m.group(4).lower() != 'bam'): skip = True
                            if not skip: inputFiles.append(os.path.join(input_dir,file))
                        elif len(mlist) == 2:
                            (file1, m1) = mlist[0]
                            (file2, m2) = mlist[1]
                            for ix in [1, 2, 4]:
                                if m1.group(ix) != m2.group(ix): break
                            else:
                                if (ftype == None or ftype == 'PAIRED') and m1.group(4) in ['fastq', 'fq', 'fasta', 'fa']:
                                    if m1.group(3) == '1' and m2.group(3) == '2':
                                        inputFiles = [os.path.join(input_dir,file1), os.path.join(input_dir,file2)]
                                    elif m1.group(3) == '2' and m2.group(3) == '1':
                                        inputFiles = [os.path.join(input_dir,file2), os.path.join(input_dir,file1)]
                                    self.ftype = 'PAIRED'
                                    self.paired = True
                        if inputFiles:
                            break
                if not inputFiles:
                    raise ValueError('Could not find input files for {} in {}'.format(fliInfo.getFli(),input_dir))

            self.curr_fli = fli
            self.curr_ftype = ftype
            self.inputFiles = inputFiles
            self.curr_output_dir = os.path.dirname(outfile)
            if not (self.dry_run or self.dry_run_json):
                self.log_parameter()
                logging.gemBS.gt("Bisulfite Mapping...")
            if self.dry_run or self.dry_run_json:
                args = self.args
                com = ['gemBS']
                if self.mem_db:
                    if Mapping.gemBS_json != 'gemBS.json':
                        com.extend(['-j',Mapping.gemBS_json])
                else:
                    if Mapping.gemBS_json != '.gemBS/gemBS.json':
                        com.extend(['-j',Mapping.gemBS_json])
                com.extend(['map','--no-merge','-D',fli])
                
                if args.ftype: com.extend(['-T',args.ftype])
                if args.paired_end: com.append('-p')
                if args.remove: com.append('-r')
                if args.threads: com.extend(['-t',args.threads])
                if args.map_threads: com.extend(['--map-threads',args.map_threads])
                if args.sort_threads: com.extend(['--sort-threads',args.sort_threads])
                if args.merge_threads: com.extend(['--merge-threads',args.mere_threads])
                if args.sort_memory: com.extend(['--sort-memory',args.sort_memory])
                if args.tmp_dir: com.extend(['-d',args.tmp_dir])
                if args.read_non_stranded: com.append('-s')
                if args.reverse_conv: com.append('-R')
                if args.benchmark_mode: com.append('--benchmark-mode')
                if args.underconversion_sequence: com.extend(['-u',args.underconversion_sequence])
                if args.overconversion_sequence: com.extend(['-v',args.overconversion_sequence])
                if not bis: com.append('--non-bs')
                if self.dry_run:
                    print(" ".join(com))
                if self.dry_run_json:
                    task = {}
                    task['command'] = com
                    task['dataset'] = fli
                    task['sample_barcode'] = self.name
                    task['inputs'] = inputFiles
                    task['index'] = self.index
                    odir = os.path.dirname(outfile)
                    report_file = os.path.join(odir,fli + '.json')
                    logfile = os.path.join(odir,'gem_mapper_' + fli + '.err')
                    task['outputs'] = [outfile, report_file, logfile]
                    desc = "map {}".format(fli)
                    self.json_commands[desc] = task
            else:
                tmp = self.tmp_dir
                if not tmp:
                    tmp = os.path.dirname(outfile)
                    
                ret = mapping(name=fli,index=self.index,fliInfo=fliInfo,inputFiles=inputFiles,ftype=ftype,filetype=filetype,
                              read_non_stranded=self.read_non_stranded, reverse_conv=self.reverse_conv,
                              outfile=outfile,paired=self.paired,tmpDir=tmp,
                              map_threads=self.map_threads,sort_threads=self.sort_threads,sort_memory=self.sort_memory,
                              under_conversion=self.underconversion_sequence,over_conversion=self.overconversion_sequence,
                              benchmark_mode=self.benchmark_mode, contig_md5=self.contig_md5, greference=self.fasta_reference) 
        
                if ret:
                    logging.gemBS.gt("Bisulfite Mapping done. Output File: %s" %(ret))
                    
            if filetype == 'SINGLE_BAM':
                self.do_merge(smp, [], outfile)
            c = self.db.cursor()
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE mapping SET status = 1 WHERE filepath = ?", (outfile,))
            database.del_db_com(outfile)
            
        c.execute("COMMIT")
        self.db.isolation_level = 'DEFERRED'
    
    def do_merge(self, sample, inputs, fname):
        if inputs:
            inputs.sort()
            self.db.isolation_level = None
            c = self.db.cursor()
            try_get_exclusive(c)
            res = c.execute("SELECT * FROM mapping WHERE sample = ?", (sample,))
            if res:
                mstat = 1
                for filename, fl, smp, ftype, status in res:
                    if ftype == 'MULTI_BAM' and status != 1: break
                    if ftype == 'MRG_BAM':
                        outfile = filename
                        mstat = status
                else:
                    if mstat == 0:
                        c.execute("UPDATE mapping SET status = 3 WHERE filepath = ?", (outfile,))
                        c.execute("COMMIT")
                        # Register output files and db cleanup in case of failure
                        odir = os.path.dirname(outfile)
                        ixfile = os.path.join(odir, smp + '.csi')
                        md5file = outfile + '.md5'
                        database.reg_db_com(outfile, "UPDATE mapping SET status = 0 WHERE filepath = '{}'".format(outfile), [outfile, ixfile, md5file])
                        if self.dry_run or self.dry_run_json:
                            args = self.args
                            com = ['gemBS']
                            if self.mem_db:
                                if Mapping.gemBS_json != 'gemBS.json':
                                    com.extend(['-j',Mapping.gemBS_json])
                            else:
                                if Mapping.gemBS_json != '.gemBS/gemBS.json':
                                    com.extend(['-j',Mapping.gemBS_json])
                            com.extend(['merge-bams','-b',sample])
                            if args.threads: com.extend(['-t',args.threads])
                            if args.remove: com.append('-r')
                            if self.dry_run:
                                print(" ".join(com))
                            if self.dry_run_json:
                                task = {}
                                task['command'] = com
                                task['sample_barcode'] = smp
                                task['inputs'] = inputs
                                logfile1 = os.path.join(odir, 'bam_index_' + smp + '.err')
                                logfile2 = os.path.join(odir, 'bam_merge_' + smp + '.err')
                                task['outputs'] = [outfile, ixfile, md5file, logfile1, logfile2]
                                desc = "merge {}".format(smp)
                                self.json_commands[desc] = task
                        else:
                            ret = merging(inputs = inputs, sample = sample, threads = self.merge_threads, outname = outfile,
                                          benchmark_mode=self.benchmark_mode, greference=self.fasta_reference)
                            if ret:
                                logging.gemBS.gt("Merging process done for {}. Output files generated: {}".format(sample, ','.join(ret)))
                                
                        try_get_exclusive(c)
                        if self.remove:
                            for f in inputs:
                                if not self.dry_run or self.dry_run_json:
                                    if os.path.exists(f): os.remove(f)
                                c.execute("UPDATE mapping SET status = 2 WHERE filepath = ?", (f,))
                        c.execute("UPDATE mapping SET status = 1 WHERE filepath = ?", (outfile,))
                        database.del_db_com(outfile)
            c.execute("COMMIT")
            self.db.isolation_level = 'DEFERRED'
        else:
            # No merging required - just create index
            if self.dry_run or self.dry_run_json:
                args = self.args
                com = ['gemBS']
                if self.mem_db:
                    if Mapping.gemBS_json != 'gemBS.json':
                        com.extend(['-j',Mapping.gemBS_json])
                else:
                    if Mapping.gemBS_json != '.gemBS/gemBS.json':
                        com.extend(['-j',Mapping.gemBS_json])
                com.extend(['merge-bams','-b',sample])
                if args.threads: com.extend(['-t',args.threads])
                if args.remove: com.append('-r')
                if self.dry_run:
                    print(' '.join(com))
                if self.dry_run_json:
                    task = {}
                    task['command'] = com
                    task['sample_barcode'] = sample
                    task['inputs'] = [fname]
                    odir = os.path.dirname(fname)
                    ixfile = os.path.join(odir, sample + '.bai')
                    md5file = fname + '.md5'
                    logfile1 = os.path.join(odir, 'bam_index_' + sample + '.err')
                    logfile2 = os.path.join(odir, 'bam_merge_' + sample + '.err')
                    task['outputs'] = [ixfile, md5file, logfile1, logfile2]
                    desc = "merge {}".format(sample)
                    self.json_commands[desc] = task
            else:
                ret = merging(inputs = [], sample = sample, threads = self.merge_threads, outname = fname)
                if ret:
                    logging.gemBS.gt("Merging process done for {}. Output files generated: {}".format(sample, ','.join(ret)))

    def extra_log(self):
        """Extra Parameters to be printed"""
        #Virtual methods, to be define in child class
        printer = logging.gemBS.gt
        
        printer("------------ Mapping Parameters ------------")
        printer("Sample barcode    : %s", self.name)
        printer("Data set          : %s", self.curr_fli)
        printer("No. threads       : %s", self.threads)
        printer("Index             : %s", self.index)
        printer("Paired            : %s", self.paired)
        printer("Read non stranded : %s", self.read_non_stranded)
        printer("Reverse conversion: %s", self.reverse_conv)
        printer("Type              : %s", self.curr_ftype)
        if self.inputFiles:
            printer("Input Files       : %s", ','.join(self.inputFiles))
        printer("Output dir        : %s", self.curr_output_dir)
        
        printer("")

class Merging(Mapping):
    title = "Merging BAMs"
    description = """Merges all bam alignments involved in a given Bisulfite project or for a given sample.
  The resulting merged BAMs are then indexed and the MD5 singatures calculated.  This is normally performed 
  automatically during the mapping stage, but may be required if gemBS is being run on a non-shared file system or the different
  datasets for a given sample are mapped by different instances of gemBS in different directories.  If the option --remove is set or 
  'remove_individual_bams' is set to True in the  configuration file then the individual BAM files will be deleted after the merge step
   has been successfully completed.  

  By default gemBS will attempt the merge for all samples, and can be restricted to a single sample using the options '-n <SAMPLE NAME>' or
  '-b <SAMPLE_BARCODE>.

  The --dry-run option will output a list of the merging operations that would be run by the merge-bam command without executing
  any of the commands.  The --json <JSON OUTPUT> options is similar to --dry-run, but writes the commands to be executed in JSON
  format to the supplied output file, including information about the input and output files for the commands.  The --ignore-db option
  modifies the --dry-run and --json options such that the database is not consulted (i.e., gemBS assumes that nothing has already
  been completed.
    """
                     
    def register(self,parser):
        ## required parameters                     
        parser.add_argument('-t', '--threads', dest="threads", metavar="THREADS", help='Number of threads, Default: %s' %self.threads)
        parser.add_argument('-n', '--sample_name',dest="sample_name",metavar="SAMPLE",help="Sample to be merged",required=False) 
        parser.add_argument('-b', '--barcode',dest="sample",metavar="SAMPLE",help="Sample to be merged",required=False) 
        parser.add_argument('-r', '--remove', dest="remove", action="store_true", help='Remove individual BAM files after merging.', required=False)
        parser.add_argument('--dry-run', dest="dry_run", action="store_true", help="Output mapping commands without execution")
        parser.add_argument('--json', dest="dry_run_json",metavar="JSON FILE",help="Output JSON file with details of pending commands")
        parser.add_argument('--ignore-db', dest="ignore_db", action="store_true",help="Ignore database for --dry-run and --json commands")
        parser.add_argument('--benchmark-mode', dest="benchmark_mode", action="store_true",help="Omit dates etc. to make file comparison simpler", required=False)
        
    def run(self, args):
        self.command = 'merge-bams'
        
        # JSON data
        self.jsonData = JSONdata(Mapping.gemBS_json)
        self.threads = self.jsonData.check(section='mapping',key='threads',arg=args.threads,default='1')
        self.merge_threads = self.jsonData.check(section='mapping',key='merge_threads',arg=args.threads,default=self.threads)
        self.remove = self.jsonData.check(section='mapping',key='remove_individual_bams',arg=args.remove, boolean=True)
        self.benchmark_mode = self.jsonData.check(section='mapping',key='benchmark_mode',arg=args.benchmark_mode, boolean=True)
        self.dry_run = args.dry_run
        self.dry_run_json = args.dry_run_json
        if self.dry_run or self.dry_run_json:
            self.ignore_db = args.ignore_db
        else:
            self.ignore_db = False
        self.args = args

        if self.dry_run_json:
            self.json_commands = {}
        
        sdata = self.jsonData.sampleData
        if not args.sample and args.sample_name:
            for k, v in sdata.items():
                if v.sample_name == args.sample_name:
                    args.sample = v.sample_barcode
                    break
            else:
                raise ValueError("Sample name '{}' not found".format(args.sample_name))
                
        # Create Dictionary of samples and bam files, checking everything required has already been made
        
        self.db = database(self.jsonData)
        self.db.check_index()
        self.mem_db = self.db.mem_db()

        # If we are doing a dry-run we will use an in memory copy of db so the on disk db is not touched
        if self.dry_run or self.dry_run_json:
            self.db.copy_to_mem()

        c = self.db.cursor()
        for fname, ftype, status in c.execute("SELECT * FROM indexing"):
            if ftype == 'gembs_reference':
                if status != 1:
                    raise CommandException("gemBS reference {} not found.  Run 'gemBS index' or correct configuration file and rerun".format(fname))
                else:
                    self.fasta_reference = fname            
        
        if args.sample:
            ret = c.execute("SELECT * from mapping WHERE sample = ?", (args.sample,))
        else:
            ret = c.execute("SELECT * from mapping")
        
        work_list = {}
        for fname, fl, smp, ftype, status in ret:
            if not smp in work_list:
                work_list[smp] = [None, [], True, False]
            if ftype == 'MRG_BAM':
                if status == 0:
                    work_list[smp][0] = fname
                else:
                    work_list[smp][3] = True
            elif ftype == 'MULTI_BAM':
                if status == 1:
                    work_list[smp][1].append(fname)
                else:
                    work_list[smp][2] = False
            else:
                if status == 0:
                    work_list[smp][2] = False
                else:
                    work_list[smp][3] = True
                    
        for smp, v in work_list.items():
            bamlist = []
            if not (v[2] or v[3]):
                logging.gemBS.gt("Not all BAM files for sample {} have been generated".format(smp))
            elif not v[0]:
                if not self.dry_run or self.dry_run_json:
                    logging.gemBS.gt("Nothing to be done for sample {}".format(smp))
            else:
                self.do_merge(smp, v[1], v[0])
                
class MethylationCall(BasicPipeline):
    title = "Methylation Calling"
    description = """Performs a methylation and SNV calling from bam aligned files. This process is performed (optionally in parallel)
   over contigs.  Smaller contigs are processed together in pools to increaes efficiency.  By default gemBS will analyze all contigs 
  / contig pools for all samples that have not already been processed. After all contigs have been processed for one sample, the
  resulting BCFs are merged into a single BCF for the sample.  This sample BCF is then indexed and the md5 signature calculated.
  If the option --remove is set or 'remove_individual_bcfs' is set to True in the configuration file then the individual BAM files will
  be deleted after the merge step has been successfully completed. The --no-merge options will prevent this automatic merging - this can be useful 
  for batch processing.

  Aside from the --no-merge option, if no disk based database is being used for gemBS and separate instances of gemBS are being run on 
  non-shared file systems then the merging will not always be performed automatically.  When the merging is not performed automatically
  for whatever reason, it can be invoked manually using the merge-bcfs command.

  The calling process can be restricted to a single sample using the option '-n <SAMPLE NAME>' or '-b <SAMPLE BARCODE>'.  The mapping
  can also be restricted to a list of contigs or contig pool using the option '-l <contig1, contig2, ...>' or '--pool <pool>'.  The 
  --list-pools option will list the available contig pools and exit.  More information on how contig pools are determined is given in
  the gemBS documentation.

  If the dbSNP_index key has been set in the configuration file (and the index has been gemerated) then this will be used by the
  caller to add public IDs in the BCF file where available.

  The locations of the input and output data are given by the configuration file; see the gemBS documentation for details.

  The --dry-run option will output a list of the calling / merging operations that would be run by the call command without executing
  any of the commands. The --json <JSON OUTPUT> options is similar to --dry-run, but writes the commands to be executed in JSON
  format to the supplied output file, including information about the input and output files for the commands. The --ignore-db option
  modifies the --dry-run and --json options such that the database is not consulted (i.e., gemBS assumes that no calling has already
  been completed but that all dependencies (i.e., BAM files) are available.  The --ignore-dep option is similar - it ignores dependencies,
  but does check whether a task has already been completed.

    """
    def membersInitiation(self):
        self.species = None
        self.chroms = None

                                   
    def register(self, parser):

        parser.add_argument('-l','--contig-list',dest="contig_list",nargs="+",metavar="CONTIGS",help="List of contigs on which to perform the methylation calling.")
        parser.add_argument('-n','--sample-name',dest="sample_name",metavar="SAMPLE",help="Name of sample to be called")  
        parser.add_argument('-b','--barcode',dest="sample",metavar="BARCODE",help="Barcode of sample to be called")  
        parser.add_argument('-q','--mapq-threshold', dest="mapq_threshold", type=int, help="Threshold for MAPQ scores")
        parser.add_argument('-Q','--qual-threshold', dest="qual_threshold", type=int, help="Threshold for base quality scores")
        parser.add_argument('-g','--right-trim', dest="right_trim", metavar="BASES", help='Bases to trim from right of read pair, Default: 0')
        parser.add_argument('-f','--left-trim', dest="left_trim", metavar="BASES", help='Bases to trim from left of read pair, Default: 5')        
        parser.add_argument('-t','--threads', dest="threads", metavar="THREADS", help='Number of threads, Default: %s' %self.threads)
        parser.add_argument('--call-threads', dest="call_threads", metavar="THREADS", help='Number of threads for calling process, Default: 1s')
        parser.add_argument('--merge-threads', dest="merge_threads", metavar="THREADS", help='Number of threads for merging process, Default: threads')
        parser.add_argument('-j','--jobs', dest="jobs", type=int, help='Number of parallel jobs')
        parser.add_argument('-u','--keep-duplicates', dest="keep_duplicates", action="store_true", help="Do not merge duplicate reads.")    
        parser.add_argument('-U','--ignore_duplicate_flag', dest="ignore_duplicates", action="store_true", help="Ignore duplicate flag from SAM/BAM files.")    
        parser.add_argument('-k','--keep-unmatched', dest="keep_unmatched", action="store_true", help="Do not discard reads that do not form proper pairs.")
        parser.add_argument('-e','--species',dest="species",metavar="SPECIES",help="Sample species name. Default: %s" %self.species)
        parser.add_argument('-r','--remove', dest="remove", action="store_true", help='Remove individual BCF files after merging.')
        parser.add_argument('-1','--haploid', dest="haploid", action="store", help="Force genotype calls to be homozygous")
        parser.add_argument('-C','--conversion', dest="conversion", help="Set under and over conversion rates (under,over)")
        parser.add_argument('-R','--reference-bias', dest="ref_bias", help="Set bias to reference homozygote")
        parser.add_argument('-x','--concat-only', dest="concat", action="store_true", help="Only perform merging BCF files.")
        parser.add_argument('--no-merge', dest="no_merge", action="store_true", help="Do not automatically merge BCFs")
        parser.add_argument('--pool',dest="req_pool",metavar="POOL",help="Contig pool on which to perform the methylation calling.")
        parser.add_argument('--list-pools',dest="list_pools",metavar="LEVEL",type=int,nargs='?',help="List contig pools and exit. Level 1 - list names, level > 1 - list pool composition", default=0, const=1)
        parser.add_argument('--dry-run', dest="dry_run", action="store_true", help="Output mapping commands without execution")
        parser.add_argument('--json', dest="dry_run_json",metavar="JSON FILE",help="Output JSON file with details of pending commands")
        parser.add_argument('--ignore-db', dest="ignore_db", action="store_true",help="Ignore database for --dry-run and --json commands")
        parser.add_argument('--ignore-dep', dest="ignore_dep", action="store_true",help="Ignore dependencies for --dry-run and --json commands")
        parser.add_argument('--benchmark-mode', dest="benchmark_mode", action="store_true",help="Omit dates etc. to make file comparison simpler", required=False)
        
    def run(self,args):
        self.command = 'call'

        # JSON data
        self.jsonData = JSONdata(MethylationCall.gemBS_json)

        if args.list_pools > 0:
            ctgs = self.jsonData.contigs
            for pool, v in ctgs.items():
                if args.list_pools == 1:
                    print(pool)
                else:
                    print(pool, v)
            return
                    
        self.threads = self.jsonData.check(section='calling',key='threads',arg=args.threads,default='1')
        self.call_threads = self.jsonData.check(section='calling',key='call_threads',arg=args.threads,default=self.threads)
        self.merge_threads = self.jsonData.check(section='calling',key='merge_threads',arg=args.threads,default=self.threads)
        self.jobs = self.jsonData.check(section='calling',key='jobs',arg=args.jobs,default=1,int_type=True)
        self.mapq_threshold = self.jsonData.check(section='calling',key='mapq_threshold',arg=args.mapq_threshold)
        self.qual_threshold = self.jsonData.check(section='calling',key='qual_threshold',arg=args.qual_threshold)
        self.left_trim = self.jsonData.check(section='calling',key='left_trim',arg=args.left_trim,default='5')
        if isinstance(self.left_trim, list):
            self.left_trim = ','.join(self.left_trim)
        self.right_trim = self.jsonData.check(section='calling',key='right_trim',arg=args.right_trim,default='0')
        if isinstance(self.right_trim, list):
            self.right_trim = ','.join(self.right_trim)
        self.ref_bias = self.jsonData.check(section='calling',key='reference_bias',arg=args.ref_bias)
        self.keep_unmatched = self.jsonData.check(section='calling',key='keep_improper_pairs',arg=args.keep_unmatched,boolean=True)
        self.keep_duplicates = self.jsonData.check(section='calling',key='keep_duplicates',arg=args.keep_duplicates,boolean=True)
        self.ignore_duplicates = self.jsonData.check(section='calling',key='ignore_duplicate_flag',arg=args.keep_duplicates,boolean=True)
        self.benchmark_mode = self.jsonData.check(section='calling',key='benchmark_mode',arg=args.benchmark_mode, boolean=True)
        self.haploid = self.jsonData.check(section='calling',key='haploid',arg=args.haploid,boolean=True)
        self.species = self.jsonData.check(section='calling',key='species',arg=args.species)
        self.contig_list = self.jsonData.check(section='calling',key='contig_list',arg=args.contig_list,list_type=True, default = [])
        self.conversion = self.jsonData.check(section='calling',key='conversion',arg=args.conversion)
        if isinstance(self.conversion, list):
            self.conversion = ','.join(self.conversion)
        self.remove = self.jsonData.check(section='calling',key='remove_individual_bcfs',arg=args.remove, boolean=True)

        self.dry_run = args.dry_run
        self.args = args
        self.dry_run_json = args.dry_run_json
        self.no_merge = args.no_merge
        if self.dry_run or self.dry_run_json:
            self.jobs = 1
            self.ignore_db = args.ignore_db
            self.ignore_dep = args.ignore_dep
        else:
            self.ignore_db = False
            self.ignore_dep = False
        if self.dry_run_json:
            self.json_commands = {}
        else:
            self.json_commands = None
        sdata = self.jsonData.sampleData
        if not args.sample and args.sample_name:
            for k, v in sdata.items():
                if v.sample_name == args.sample_name:
                    args.sample = v.sample_barcode
                    break
            else:
                raise ValueError("Sample name '{}' not found".format(args.sample_name))

        if self.contig_list != None:
            if len(self.contig_list) == 1:
                if os.path.isfile(self.contig_list[0]):
                    #Check if contig_list is a file or just a list of chromosomes
                    #Parse file to extract chromosome list 
                    tmp_list = []
                    with open(self.contig_list[0] , 'r') as chromFile:
                        for line in chromFile:
                            tmp_list.append(line.split()[0])
                        self.contig_list = tmp_list
                        self.jsonData.config['calling']['contig_list'] = tmp_list
                        
        self.db = database(self.jsonData)
        self.mem_db = self.db.mem_db()
        if not self.mem_db:
            self.db.check_index()
            
        # If we are doing a dry-run we will use an in memory copy of the db so the on disk db is not touched
        if self.dry_run or self.dry_run_json:
            self.db.copy_to_mem()

        c = self.db.cursor()

        self.sample_conversion = {}
        
        if self.conversion != None and self.conversion.lower() == "auto" and not args.concat:
            sample_lane_files = {}
            if args.sample:
                ret = c.execute("SELECT filepath, fileid, sample FROM mapping WHERE sample = ? AND type != 'MRG_BAM'", (args.sample,))
            else:
                ret = c.execute("SELECT filepath, fileid, sample FROM mapping WHERE type != 'MRG_BAM'")
                
            for fname, fli, smp in ret:
                bam_dir = os.path.dirname(fname)
                fileJson = os.path.join(bam_dir,"{}.json".format(fli))
                if os.path.isfile(fileJson):
                    if smp not in sample_lane_files: 
                        sample_lane_files[smp] = {}
                        sample_lane_files[smp][fli] = [fileJson]
                    elif fli not in sample_lane_files[smp]:
                        sample_lane_files[smp][fli] = [fileJson]
                    else:
                        sample_lane_files[smp][fli].append(fileJson)
                
            if len(sample_lane_files) < 1:
                self.conversion = None
            else:
                for sample,fli_json in sample_lane_files.items():
                    list_stats_lanes = []
                    for fli,json_files in fli_json.items():  
                        for json_file in json_files:
                            lane = LaneStats(name=fli,json_file=json_file)
                            list_stats_lanes.append(lane)
                    stats = SampleStats(name=sample,list_lane_stats=list_stats_lanes)
                    uc = stats.getUnderConversionRate()
                    oc = stats.getOverConversionRate()
                    if uc == "NA" or uc < 0.0:
                        uc = 0.99
                    elif uc < 0.95:
                        uc = 0.95
                    elif uc > 0.999:
                        uc = 0.999
                    if oc == "NA" or oc < 0.0:
                        oc = 0.05
                    elif oc > 0.15:
                        oc = 0.15
                    elif oc < 0.001:
                        oc = 0.01
                    self.sample_conversion[sample] = "{:.4f},{:.4f}".format(1-uc,oc)

        # Get fasta reference && dbSNP index if supplied
        self.dbSNP_index_file = None
        for fname, ftype, status in c.execute("SELECT * FROM indexing"):
            if ftype == 'gembs_reference':
                if status != 1:
                    raise CommandException("gemBS reference {} not found.  Run 'gemBS index' or correct configuration file and rerun".format(fname))
                else:
                    self.fasta_reference = fname            
            elif ftype == 'dbsnp_idx':
                if status != 1:
                    raise CommandException("dbSNP index {} not found.  Run 'gemBS index' or correct configuration file and rerun".format(fname))
                else:
                    self.dbSNP_index_file = fname
                
        #Check input bam existance
        
        sampleBam = {}
        if args.sample:
            ret = c.execute("SELECT * from mapping WHERE (sample = ?) AND (type != 'MULTI_BAM')", (args.sample,))
        else:            
            ret = c.execute("SELECT * from mapping WHERE type != 'MULTI_BAM'")
        for fname, fli, smp, ftype, status in ret:
            if status == 1 or self.ignore_db or self.ignore_dep:
                if not os.path.isfile(fname):
                    if not (self.ignore_db or self.ignore_dep):
                        raise CommandException("Sorry file '{}' was not found".format(fname))
                sampleBam[smp] = fname
            else:
                logging.gemBS.gt("Sample BAM file '{}' not ready".format(fname))

        if not sampleBam:
            raise CommandException("No available BAM files for calling")

        # Get contig pools
        contigs = self.jsonData.contigs
        
        if self.contig_list:
            tmp_list = []
            ctg_pool = {}
            for pl, v in contigs.items():
                for ctg in v:
                    ctg_pool[ctg] = pl
            for ctg in self.contig_list:
                pl = ctg_pool[ctg]
                if not pl in tmp_list:
                    tmp_list.append(pl)
            self.contig_list = tmp_list
        else:
            self.contig_list = list(contigs.keys())

        if args.req_pool:
            if args.req_pool in self.contig_list:
                self.contig_list = [args.req_pool]
            else:
                self.contig_list = []
            
        # Get output files
        ind_bcf = {}
        mrg_bcf = {}
        for smp in sampleBam:
            ind_bcf[smp] = []
        for fname, pool, smp, psize, ftype, status in c.execute("SELECT * from calling"):
            if self.ignore_db:
                status = 0
            if smp in sampleBam:
                if ftype == 'POOL_BCF':
                    if pool in self.contig_list:
                        ind_bcf[smp].append((fname, status, pool, contigs[pool]))
                else:
                    mrg_bcf[smp] = (fname, status)

        self.sampleBam = {}
        self.outputBcf = {}
        for smp, fname in sampleBam.items():
            if mrg_bcf[smp][1] == 0:
                call = False
                for v in ind_bcf[smp]:
                    if v[1] == 0:
                        if not smp in self.outputBcf:
                            self.outputBcf[smp] = [(v[0], v[2], v[3])]
                        else:
                            self.outputBcf[smp].append((v[0], v[2], v[3]))
                        call = True
                if call:
                    self.sampleBam[smp] = fname
                
        self.input = list(self.sampleBam.values())
        self.samples = list(sampleBam.keys())
        self.output = []
        for smp, pl in self.outputBcf.items():
            for v in pl:
                self.output.append(v[0])
        
        # Call for requested list
        mrg = False
        if not self.output:
            for smp, v in mrg_bcf.items():
                if v[1] == 0:
                    mrg = True
                    break
            else:
                if not (self.dry_run or self.dry_run_json):
                    if args.concat:
                        logging.gemBS.gt("No merging to be performed")
                    else:
                        logging.gemBS.gt("No calling to be performed")
        if self.output or mrg:
            if self.dry_run or self.dry_run_json:
                com = ['gemBS']
                if self.mem_db:
                    if Mapping.gemBS_json != 'gemBS.json':
                        com.extend(['-j',Mapping.gemBS_json])
                else:
                    if Mapping.gemBS_json != '.gemBS/gemBS.json':
                        com.extend(['-j',Mapping.gemBS_json])
                com1 = []
                if args.threads != None: com1.extend(['-t',args.threads])
                if args.call_threads != None: com1.extend(['--call-threads',args.call_threads])
                if args.merge_threads != None: com1.extend(['--merge-threads',args.merge_threads])
                if args.remove != None: com1.append('-r')
                com2 = []
                if args.mapq_threshold != None: com2.extend(['-q',str(args.mapq_threshold)])
                if args.qual_threshold != None: com2.extend(['-Q',str(args.mapq_threshold)])
                if args.right_trim != None: com2.extend(['--right-trim',str(args.right_trim)])
                if args.left_trim != None: com2.extend(['--left-trim',str(args.left_trim)])
                if args.conversion != None: com2.extend(['--conversion',str(args.conversion)])
                if args.keep_duplicates != None: com2.append('-u')
                if args.ignore_duplicates != None: com2.append('-U')
                if args.keep_unmatched != None: com2.append('-k')
                if args.haploid != None: com2.append('--haploid')
                if args.species != None: com2.append('--species')
                if args.benchmark_mode: com.append('--benchmark-mode')
                if args.ref_bias != None: com2.extend(['-B',args.ref_bias])
                dry_run_com = [com, com1, com2]
                
            else:
                dry_run_com = None
                self.log_parameter()
                if args.concat:
                    logging.gemBS.gt("Methylation Merging...")
                else:
                    logging.gemBS.gt("Methylation Calling...")
            ret = methylationCalling(reference=self.fasta_reference,species=self.species,no_merge=self.no_merge,ignore_db=self.ignore_db,
                                     right_trim=self.right_trim, left_trim=self.left_trim,concat=args.concat,json_commands=self.json_commands,
                                     sample_bam=self.sampleBam,output_bcf=self.outputBcf,remove=self.remove,dry_run=self.dry_run,
                                     keep_unmatched=self.keep_unmatched,samples=self.samples,dry_run_com=dry_run_com,
                                     keep_duplicates=self.keep_duplicates,ignore_duplicates=self.ignore_duplicates,
                                     dbSNP_index_file=self.dbSNP_index_file,call_threads=self.call_threads,merge_threads=self.merge_threads,jobs=self.jobs,
                                     mapq_threshold=self.mapq_threshold,bq_threshold=self.qual_threshold,dry_run_json=self.dry_run_json,
                                     haploid=self.haploid,conversion=self.conversion,ref_bias=self.ref_bias,sample_conversion=self.sample_conversion,
                                     benchmark_mode=self.benchmark_mode)
                
            if ret and not (self.dry_run or self.dry_run_json):
                if args.concat:
                    logging.gemBS.gt("Methylation merging done, samples performed: %s" %(ret))
                else:
                    logging.gemBS.gt("Methylation call done, samples performed: %s" %(ret))

        if self.dry_run_json and self.json_commands:
            with open(self.dry_run_json, 'w') as of:
                json.dump(self.json_commands, of, indent = 2)
                
    def extra_log(self):
        """Extra Parameters to be printed"""
        #Virtual methods, to be define in child class
        printer = logging.gemBS.gt
        
        printer("----------- Methylation Calling --------")
        printer("Reference       : %s", self.fasta_reference)
        printer("Species         : %s", self.species)
        printer("Right Trim      : %s", self.right_trim)
        printer("Left Trim       : %s", self.left_trim)
        printer("Chromosomes     : %s", self.contig_list)
        printer("Threads         : %s", self.threads)
        if self.dbSNP_index_file:
            printer("dbSNP File      : %s", self.dbSNP_index_file)
        for sample,input_bam in self.sampleBam.items():
            printer("Sample: %s    Bam: %s" %(sample,input_bam))
        printer("")

class BsCallConcatenate(MethylationCall):
    title = "Merging BCFs."  
    description = """Merges all BCF call files involved in a given Bisulfite project or for a given sample. The resulting merged BCFs are 
  then indexed and the MD5 singatures calculated.  This is normally performed automatically during the calling stage, but may be required
  if gemBS is being run on a non-shared file system or the different datasets for a given sample  are mapped by different instances of gemBS
  in different directories.  If the option --remove is set or 'remove_individual_bams' is set to True in the  configuration file then the 
  individual BAM files will be deleted after the merge step  has been successfully completed.  

  By default gemBS will attempt the merge for all samples, and can be restricted to a single sample using the options '-n <SAMPLE NAME>' or
  '-b <SAMPLE_BARCODE>.

  The --dry-run option will output a list of the merging operations that would be run by the merge-bcfs command without executing
  any of the commands. The --json <JSON OUTPUT> options is similar to --dry-run, but writes the commands to be executed in JSON
  format to the supplied output file, including information about the input and output files for the commands. The --ignore-db option
  modifies the --dry-run and --json options such that the database is not consulted (i.e., gemBS assumes that no calling has already
  been completed but that all dependencies (i.e., BAM files) are available.  The --ignore-dep option is similar - it ignores dependencies,
  but does check whether a task has already been completed.

    """
    
    def register(self,parser):

        parser.add_argument('-n', '--sample-name',dest="sample_name",metavar="SAMPLE",help="Nmae of sample to be merged",required=False)
        parser.add_argument('-b', '--sample-barcode',dest="sample",metavar="BARCODE",help="Barcode of sample to be merged",required=False)
        parser.add_argument('-t', '--threads', dest="threads", metavar="THREADS", help='Number of threads')
        parser.add_argument('--merge-threads', dest="merge_threads", metavar="THREADS", help='Number of threads for merge step')
        parser.add_argument('-r', '--remove', dest="remove", action="store_true", help='Remove individual BAM files after merging.', required=False)
        parser.add_argument('-j', '--jobs', dest="jobs", type=int, help='Number of parallel jobs')
        parser.add_argument('--dry-run', dest="dry_run", action="store_true", help="Output mapping commands without execution")
        parser.add_argument('--json', dest="dry_run_json",metavar="JSON FILE",help="Output JSON file with details of pending commands")
        parser.add_argument('--ignore-db', dest="ignore_db", action="store_true",help="Ignore database for --dry-run and --json commands")
        parser.add_argument('--ignore-dep', dest="ignore_dep", action="store_true",help="Ignore dependencies for --dry-run and --json commands")
        parser.add_argument('--benchmark-mode', dest="benchmark_mode", action="store_true",help="Omit dates etc. to make file comparison simpler", required=False)
    
    def run(self,args):

        args.concat = True
        args.req_pool = None
        args.mapq_threshold = None
        args.qual_threshold = None
        args.contig_list = None
        args.right_trim = None
        args.left_trim = None
        args.keep_duplicates = None
        args.keep_unmatched = None
        args.species = None
        args.haploid = None
        args.conversion = None
        args.ref_bias = None
        args.dbSNP_index_file = None
        args.pool = None
        args.list_pools = 0
        args.call_threads = None
        args.no_merge = False
        MethylationCall.run(self, args)
      
class MethylationFilteringThread(th.Thread):
    def __init__(self, threadID, methFilt, lock):
        th.Thread.__init__(self)
        self.threadID = threadID
        self.methFilt = methFilt
        self.bcf_list = methFilt.bcf_list
        self.lock = lock

    def run(self):
        while self.bcf_list:
            self.lock.acquire()
            if self.bcf_list:
                v = self.bcf_list.pop(0)
                self.lock.release()
                self.methFilt.do_filter(v)
            else:
                self.lock.release()
            
class MethylationFiltering(BasicPipeline):
    title = "Methylation & SNP Extraction."
    description = """ 
  Extracts summary files from BCF files generated for all or a subset of samples to produce a series of summary output files.  The detailed formats of the 
  output files are given in the gemBS docuemntation.

  The default output are CpG files.  These are BED3+8 format files with information on methylation and genotypes.  A list of non-CpG sites
  in the same basic format can also be produced.  Various options on filtering these files on genotype quality and coverage  are
  available.  By default the CpG files have 1 output line per CpG (so the information from the two strands is combined).  This can be changed
  to give strand specific information using the -s option.  Standard filtering strategy is to only output sites where the sample genotype is 
  called as being homozygous CG/CG with a phred score >= to the theshold set using the -q option (default 20).  Using the --allow-het option 
  will allow heterozygous CpG sites to be included in the output.  The sitest can also be filtered on minimum informative coverage using the 
  -I option (default = 1).  For non-CpG sites the strategy is to only output sites with a minimum number of non-converted reads.  This level
  can be set using the --min-nc option (default = 1).

  A second set of extracted outputs that correspond to the ENCODE WGBS pipeline are also available using the --bed-methyl and --bigwig options.
  The --bed-methyl option will produce three files per sample for all covered sites in CpG, CHG and CHH context in BED9+5 format.  Each of 
  the files will also be generated in bigBed format for display in genome browsers.  In addition a bigWig format file will be generated giving
  the methylation percentage at all covered cytosine sites (informative coverage > 0).  If the --strand-specific option is given then two bigWig
  files will be geenrated - one for each strand.  For the ENCODE output files, not further filtering is performed.

  In addition to the methylation result, SNP genotypes can also be extracted with the --snps options.  By default, this will return a file
  with genotypes on all SNPs covered by the experiment that were in the dbSNP_idx file used for the calling stage.  This selection can
  be refined uwing the --snp-list option, which is a file with a list of SNP ids, one id per line.  An alternate dbSNP_idx file can also be supplied
  using the --snp-db option, allowing SNPs that were not in the original dbSNP_idx file used for calling to be extracted.

  The --dry-run option will output a list of the merging operations that would be run by the merge-bcfs command without executing
  any of the commands. The --json <JSON OUTPUT> options is similar to --dry-run, but writes the commands to be executed in JSON
  format to the supplied output file, including information about the input and output files for the commands. The --ignore-db option
  modifies the --dry-run and --json options such that the database is not consulted (i.e., gemBS assumes that no calling has already
  been completed but that all dependencies (i.e., BAM files) are available.  The --ignore-dep option is similar - it ignores dependencies,
  but does check whether a task has already been completed.

    """
                  
    def register(self,parser):
        ## required parameters
        parser.add_argument('-j','--jobs', dest="jobs", type=int, help='Number of parallel jobs')
        parser.add_argument('-n','--sample-name',dest="sample_name",metavar="SAMPLE_NAME",help="Name of sample to be filtered")  
        parser.add_argument('-b','--barcode',dest="sample",metavar="SAMPLE_BARCODE",help="Barcode of sample to be filtered")  
        parser.add_argument('-s','--strand-specific', dest="strand_specific", action="store_true", default=False, help="Output separate lines in CpG file for each strand.")
        parser.add_argument('-W','--bigwig-strand-specific', dest="bw_strand_specific", action="store_true", default=False, help="Output separate bigWig files for each strand.")
        parser.add_argument('-q','--phred-threshold', dest="phred", help="Min threshold for genotype phred score.")
        parser.add_argument('-I','--min-inform', dest="inform", help="Min threshold for informative reads.")
        parser.add_argument('-M','--min-nc', dest="min_nc", help="Min threshold for non-converted reads for non CpG sites.")
        parser.add_argument('-H','--allow-het', dest="allow_het", action="store_true", help="Allow both heterozygous and homozgyous sites.")
        parser.add_argument('-R','--reference-bias', dest="ref_bias", help="Allow both heterozygous and homozgyous sites.")
        parser.add_argument('-c','--cpg', dest="cpg", action="store_true", help="Output gemBS bed with cpg sites.")
        parser.add_argument('-N','--non-cpg', dest="non_cpg", action="store_true", help="Output gemBS bed with non-cpg sites.")
        parser.add_argument('-B','--bed-methyl', dest="bedMethyl", action="store_true", help="Output bedMethyl files (bed and bigBed)")
        parser.add_argument('-S','--snps', dest="snps", action="store_true",help="Output SNPs")
        parser.add_argument('-t','--extract-threads', dest="extract_threads", metavar="THREADS", help='Number of extra threads for extract step')
        parser.add_argument('--snp-list', dest="snp_list", help="List of SNPs to output")
        parser.add_argument('--snp-db', dest="snp_db", help="dbSNP_idx processed SNP idx")
        parser.add_argument('--dry-run', dest="dry_run", action="store_true", help="Output mapping commands without execution")
        parser.add_argument('--json', dest="dry_run_json",metavar="JSON FILE",help="Output JSON file with details of pending commands")
        parser.add_argument('--ignore-db', dest="ignore_db", action="store_true",help="Ignore database for --dry-run and --json commands")
        parser.add_argument('--ignore-dep', dest="ignore_dep", action="store_true",help="Ignore dependencies for --dry-run and --json commands")
        
    def run(self,args):
        self.command = 'extract'

        # JSON data
        self.jsonData = JSONdata(Mapping.gemBS_json)

        self.threads = self.jsonData.check(section='extract',key='threads')
        self.extract_threads = self.jsonData.check(section='extract',key='extract_threads',arg=args.extract_threads,default=self.threads)
        self.jobs = self.jsonData.check(section='extract',key='jobs',arg=args.jobs,default=1,int_type=True)
        self.allow_het = self.jsonData.check(section='extract',key='allow_het',arg=args.allow_het,boolean=True,default=False)
        self.cpg = self.jsonData.check(section='extract',key='make_cpg',arg=args.cpg,boolean=True,default=False)
        self.snps = self.jsonData.check(section='extract',key='make_snps',arg=args.snps,boolean=True,default=False)
        self.snp_list = self.jsonData.check(section='extract',key='snp_list',arg=args.snp_list)
        self.snp_db = self.jsonData.check(section='extract',key='snp_db',arg=args.snp_db)
        self.non_cpg = self.jsonData.check(section='extract',key='make_non_cpg',arg=args.non_cpg,boolean=True,default=False)
        self.bedMethyl = self.jsonData.check(section='extract',key='make_bedmethyl',arg=args.bedMethyl,boolean=True,default=False)
        self.ref_bias = self.jsonData.check(section='extract',key='reference_bias',arg=args.ref_bias)
#        self.bigWig = self.jsonData.check(section='extract',key='make_bigwig',arg=args.bigWig,boolean=True,default=False)
        self.strand_specific = self.jsonData.check(section='extract',key='strand_specific',arg=args.strand_specific,boolean=True,default=False)
        self.bw_strand_specific = self.jsonData.check(section='extract',key='bigwig_strand_specific',arg=args.bw_strand_specific,boolean=True,default=False)
        self.phred = self.jsonData.check(section='extract',key='phred_threshold',arg=args.phred, default = '20')
        self.inform = self.jsonData.check(section='extract',key='min_inform',arg=args.inform, default = 1, int_type=True)
        self.min_nc = self.jsonData.check(section='extract',key='min_nc',arg=args.inform, default = 1, int_type=True)
        self.path_bcf = self.jsonData.check(section='calling',key='bcf_dir',arg=None, default = '.', dir_type=True)
        self.dry_run = args.dry_run
        self.dry_run_json = args.dry_run_json

        if self.dry_run or self.dry_run_json:
            self.jobs = 1
            self.ignore_db = args.ignore_db
            self.ignore_dep = args.ignore_dep
            self.args = args
        else:
            self.ignore_db = False
            self.ignore_dep = False
        if self.dry_run_json:
            self.json_commands = {}
        else:
            self.json_commands = None

        if not (self.cpg or self.non_cpg or self.bedMethyl or self.snps):
            self.cpg = True

        self.mask = 0
        if self.cpg: self.mask |= 3
        if self.non_cpg: self.mask |= 12
        if self.bedMethyl: self.mask |= 48
#        if self.bigWig: self.mask |= 192
        if self.snps: self.mask |= 768
        self.mask1 = self.mask & 341
        
        sdata = self.jsonData.sampleData
        if not args.sample and args.sample_name:
            for k, v in sdata.items():
                if v.sample_name == args.sample_name:
                    args.sample = v.sample_barcode
                    break
            else:
                raise ValueError("Sample name '{}' not found".format(args.sample_name))
                
        db = database(self.jsonData)
        self.mem_db = db.mem_db()
        if not self.mem_db:
            db.check_index()        
            db.check_extract()

        # If we are doing a dry-run we will use an in memory copy of the db so the on disk db is not touched
        if self.dry_run or self.dry_run_json:
            db.copy_to_mem()

        c = db.cursor()
        c.execute("SELECT * FROM indexing WHERE type = 'contig_sizes'")
        ret = c.fetchone()
        if not ret or ret[2] != 1:
            raise CommandException("Could not open contig sizes file.")
        self.contig_size_file = ret[0]
        contig_size = {}
        with open (self.contig_size_file, "r") as f:
            for line in f:
                fd = line.split()
                if(len(fd) > 1):
                    contig_size[fd[0]] = int(fd[1])

        self.contig_list = []
        for ctg in self.jsonData.pools:
            self.contig_list.append((ctg, contig_size[ctg]))
        self.contig_list.sort(key = lambda x: x[0])
        
        self.bcf_list = []
        if args.sample:
            ret = c.execute("SELECT filepath, sample, status from calling WHERE sample = ? AND type = 'MRG_BCF'", (args.sample,))
        else:
            ret = c.execute("SELECT filepath, sample, status from calling WHERE type = 'MRG_BCF'")
        for fname, smp, status in ret:
            if status == 1 or self.ignore_db or self.ignore_dep:
                self.bcf_list.append((smp, fname))

        if not self.bcf_list:
            logging.gemBS.gt("No BCF files are available for methylation extraction.")
        else:
            if self.jobs > len(self.bcf_list):
                self.jobs = len(self.bcf_list)
            self.threads = self.jobs
            self.log_parameter()
            logging.gemBS.gt("Methylation Extraction...")
            if self.jobs > 1:
                threads = []
                lock = th.Lock()
                for ix in range(self.jobs):
                    thread = MethylationFilteringThread(ix, self, lock)
                    thread.start()
                    threads.append(thread)
                for thread in threads:
                    thread.join()
            else:
                for v in self.bcf_list:
                    self.do_filter(v)
                
        if self.dry_run_json and self.json_commands:
            with open(self.dry_run_json, 'w') as of:
                json.dump(self.json_commands, of, indent = 2)

    def do_filter(self, v):
        sample, bcf_file = v
        self.bcf_file = bcf_file
        db = database()
        db.isolation_level = None
        c = db.cursor()

        try_get_exclusive(c)
        
        c.execute("SELECT filepath, status FROM extract WHERE sample = ?", (sample,))
        ret = c.fetchone()
        if ret:
            filebase, status = ret
            old_stat = status
            sm = status & self.mask
            if self.ignore_db:
                sm = 0
            if not (sm == self.mask or sm == self.mask1):
                status1 = status | self.mask
                c.execute("UPDATE extract SET status = ? WHERE filepath = ?", (status1, filebase))
                c.execute("COMMIT")
                files = [filebase + "_contig_list.bed"]
                cpg, non_cpg, bigWig, bedMethyl, snps = (False, False, False, False, False)
                if self.cpg and not (sm & 3):
                    cpg = True
                    files.extend([filebase + '_cpg.txt.gz', filebase + '_cpg.txt.gz.tbi', filebase + '_cpg.txt.gz.md5'])
                if self.non_cpg and not (sm & 12):
                    non_cpg = True
                    files.extend([filebase + '_non_cpg.txt.gz', filebase + '_non_cpg.txt.gz.tbi', filebase + '_non_cpg.txt.gz.md5'])
                if self.bedMethyl and not (sm & 192):
                    bedMethyl = True
                    for x in ('cpg', 'chg', 'chh'):
                        files.extend([filebase + "_{}.bed.gz".format(x), filebase + "_{}.bed.gz.md5".format(x), 
                                      filebase + "_{}.bb".format(x), filebase + "_{}.bb.md5".format(x)])
                    if self.bw_strand_specific:
                        for x in ('pos', 'neg'):
                            files.extend([filebase + '_{}.bw'.format(x), filebase + '_{}.bw.md5'.format(x)])
                    else:
                        files.extend([filebase + '.bw', filebase + '.bw.md5'])
                        
                if self.snps and not(sm & 768):
                    snps = True
                    files.extend([filebase + '_snps.txt.gz', filebase + '_snps.txt.gz_tbi', filebase + '_snps.txt.gz.md5'])

                if self.dry_run or self.dry_run_json:
                    args = self.args
                    com = ['gemBS']
                    if self.mem_db:
                        if Mapping.gemBS_json != 'gemBS.json':
                            com.extend(['-j',Mapping.gemBS_json])
                    else:
                        if Mapping.gemBS_json != '.gemBS/gemBS.json':
                            com.extend(['-j',Mapping.gemBS_json])
                    com.extend(['extract','-b',sample])
                    if args.strand_specific: com.append('-s')
                    if args.bw_strand_specific: com.append('-W')
                    if args.phred: com.extend(['-q', args.phred])
                    if args.inform: com.extend(['-I', args.inform])
                    if args.min_nc: com.extend(['-M', args.min_nc])
                    if args.ref_bias: com.extend(['--reference-bias', args.ref_bias])
                    if args.allow_het: com.extend(['-H', args.allow_het])
                    if args.extract_threads: com.extend(['-@', args.extract_threads])
                    if cpg: com.append('--cpg')
                    if non_cpg: com.append('--non-cpg')
#                    if bigWig: com.append('--bigwig')
                    if bedMethyl: com.append('--bed-methyl')
                    if snps:
                        com.append('--snps')
                        if args.snp_list: com.extend(['--snp_list', args.snp_list])
                        if args.snp_db: com.extend(['--snp_db', args.snp_db])
                    if self.dry_run:
                        print(' '.join(com))
                    if self.dry_run_json:
                        task = {}
                        desc = "extract {}".format(sample)
                        task['command'] = com
                        task['sample_barcode'] = sample
                        task['inputs'] = [bcf_file]
                        odir = os.path.dirname(filebase)
                        if cpg or non_cpg or bedMethyl or bigWig:
                            files.append(os.path.join(odir, 'mextr_{}.err'.format(sample)))
                        if snps:
                            files.append(os.path.join(odir, 'snpxtr_{}.err'.format(sample)))
                        task['outputs'] = files[1:]
                        self.json_commands[desc] = task
                else:
                    database.reg_db_com(filebase, "UPDATE extract SET status = 0 WHERE filepath = '{}'".format(filebase), files)                

                    #Call methylation extract
                    ret = methylationFiltering(bcfFile=bcf_file,outbase=filebase,name=sample,strand_specific=self.strand_specific,bw_strand_specific=self.bw_strand_specific,
                                               cpg=cpg,non_cpg=non_cpg,contig_list=self.contig_list,allow_het=self.allow_het,
                                               inform=self.inform,phred=self.phred,min_nc=self.min_nc,bedMethyl=bedMethyl,
                                               bigWig=bigWig,contig_size_file=self.contig_size_file,ref_bias=self.ref_bias,
                                               snps=snps,snp_list=self.snp_list,snp_db=self.snp_db,extract_threads=self.extract_threads)
                    if ret:
                        logging.gemBS.gt("Results extraction for {} done, results located in: {}".format(bcf_file, ret))

                    status1 = (old_stat | self.mask1) & 341
                    database.del_db_com(filebase)
                c.execute("BEGIN IMMEDIATE")
                c.execute("UPDATE extract SET status = ? WHERE filepath = ?", (status1, filebase))
               
        c.execute("COMMIT")
        db.close()
        
    def extra_log(self):
        """Extra Parameters to be printed"""
        #Virtual methods, to be define in child class
        
class MappingReports(BasicPipeline):
    title = "Bisulfite Mapping reports"
    description = """Bisulfite mapping report generation.  Builds a HTML and SPHINX report per dataset and sample """
    
    def register(self,parser):
        ## Mapping report stats parameters
        parser.add_argument('-p', '--project', dest="project", metavar="PROJECT", help='Output title for report (project name)')
        parser.add_argument('-o', '--output-dir', dest="output_dir", metavar="PATH",help='Output directory to store html mapping report.')
         
         
    def run(self, args):
        self.command = 'map-report'

        # JSON data
        self.jsonData = JSONdata(MethylationCall.gemBS_json)
        
        self.project = self.jsonData.check(section='report',key='project',arg=args.project, default='gemBS')
        self.output_dir = self.jsonData.check(section='report',key='report_dir',arg=args.output_dir,dir_type=True,default='gemBS_reports')

        self.output_dir = os.path.join(self.output_dir, 'mapping')

        # Make list of JSON mapping report files from db
        
        db = database(self.jsonData)
        sample_files = {}   
        c = db.cursor()
        sample_missing = {}
        for fname, fli, smp, status in c.execute("SELECT filepath, fileid, sample, status FROM MAPPING WHERE type != 'MRG_BAM'"):
            ok = False
            fileJson = os.path.join(os.path.dirname(fname), "{}.json".format(fli))
            if status != 0:
                if os.path.isfile(fileJson):
                    ok = True
                    if smp not in sample_files: 
                        sample_files[smp] = [(fli,fileJson)]
                    else:
                        sample_files[smp].append((fli,fileJson))
            if not ok:
                if not smp in sample_missing:
                    sample_missing[smp] = [fileJson]
                else:
                    sample_missing[smp].append(fileJson)

        if sample_missing:
            logging.gemBS.gt("The following samples have some JSON report files missing so the report will not be complete:")
            for smp, v in sample_missing.items():
                logging.gemBS.gt("{}: {}".format(smp, v))
                
        # Check list of files
        if len(sample_files) < 1:
            raise CommandException("Sorry no JSON files were found")

        self.log_parameter()
        logging.gemBS.gt("Building html reports...")
        htmlBuildReport(inputs=sample_files,output_dir=self.output_dir,name=self.project)
        logging.gemBS.gt("Building sphinx reports...")
        sphinxBuildReport(inputs=sample_files,output_dir="%s/SPHINX/" %(self.output_dir),name=self.project)
        logging.gemBS.gt("Report Done.")
         
    def extra_log(self):
        """Extra Parameters to be printed"""
        #Virtual methods, to be define in child class
        printer = logging.gemBS.gt
        
        printer("------- Mapping Report ----------")
        printer("Title           : %s", self.project)
        printer("Output dir      : %s", self.output_dir)
        printer("")             
        
class VariantsReports(BasicPipeline):
    title = "BS Calls reports"
    description = """BS call report generation.  Builds a HTML and SPHINX report per Sample"""

    def register(self,parser):
        ## variants reports stats parameters
        parser.add_argument('-p', '--project', dest="project", metavar="PROJECT", help='Output title for report (project name)')
        parser.add_argument('-o', '--output-dir', dest="output_dir", metavar="PATH",help='Output directory to store html and Sphinx Variants report.')
        parser.add_argument('-t', '--threads', dest="threads", type=int,help='Number of jobs to run in parallel.')
        
    def run(self, args):
        self.command = 'variants-report'

        # JSON data
        self.jsonData = JSONdata(MethylationCall.gemBS_json)
        
        self.project = self.jsonData.check(section='report',key='project',arg=args.project, default='gemBS')
        self.output_dir = self.jsonData.check(section='report',key='report_dir',arg=args.output_dir,dir_type=True,default='gemBS_reports')
        self.threads = self.jsonData.check(section='calling',key='threads',arg=args.threads,default='1')

        self.output_dir = os.path.join(self.output_dir, 'variant_calling')

        # Get list of JSON variant calling report files from db
        db = database(self.jsonData)
        c = db.cursor()
        sample_files = {}
        sample_missing = {}
        for fname, fli, smp, status in c.execute("SELECT filepath, poolid, sample, status FROM CALLING WHERE type == 'POOL_BCF'"):
            fileJson = os.path.splitext(fname)[0] + '.json'
            ok = False
            if status != 0:
                if os.path.isfile(fileJson):
                    ok = True
                    if not smp in sample_files:
                        sample_files[smp] = [fileJson]
                    else:
                        sample_files[smp].append(fileJson)
            if not ok:
                if not smp in sample_missing:
                    sample_missing[smp] = [fileJson]
                else:
                    sample_missing[smp].append(fileJson)

        if sample_missing:
            logging.gemBS.gt("The following samples have some JSON report files missing so the report will not be complete:")
            for smp, v in sample_missing.items():
                logging.gemBS.gt("{}: {}".format(smp, v))                        

        self.log_parameter()
        logging.gemBS.gt("Building variant calls html and sphinx reports...")
        buildBscallReports(inputs=sample_files,output_dir=self.output_dir,name=self.project,threads=int(self.threads))
        logging.gemBS.gt("Report Done.")                         

    def extra_log(self):
        """Extra Parameters to be printed"""
        #Virtual methos, to be define in child class
        printer = logging.gemBS.gt
        
        printer("------- Variants Report ----------")
        printer("Title           : %s", self.project)
        printer("Output dir      : %s", self.output_dir)
        printer("")   
        
class dbSync(BasicPipeline):
    title = "Synchronize database"
    description = """Synchronize database with filesystem"""

    def register(self,parser):
        ## variants reports stats parameters
        parser.add_argument('-y', '--yes', action = 'store_true', dest="confirm", help='Confirm operation')
        
    def run(self, args):
        self.command = 'synchromize database'

        # JSON data
        self.jsonData = JSONdata(MethylationCall.gemBS_json)

        if not args.confirm:
            print("Attention! This command must not be run if other gemBS commands are still running")
            resp = input("Please enter 'y' to confirm: ")
            if resp.lower().startswith('y'):
                args.confirm = True

        if args.confirm:
            logging.gemBS.gt("Synchronizing database")
            db = database(self.jsonData,sync = True)
        
