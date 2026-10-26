#!/usr/bin/env perl
# result_aggregator.pl - Aggregate firmware test results across multiple CI runs
# Combines JUnit XML files, calculates statistics, identifies flaky tests

use strict;
use warnings;
use File::Find;
use File::Basename;
use Getopt::Long;
use POSIX qw(strftime);

my $input_dir    = 'reports/junit/';
my $output_csv   = 'reports/aggregated_results.csv';
my $output_txt   = 'reports/aggregated_summary.txt';
my $flaky_thresh = 0.1;   # 10-90% pass rate = flaky
my $help         = 0;

GetOptions(
    'input-dir=s'      => \$input_dir,
    'output-csv=s'     => \$output_csv,
    'output-txt=s'     => \$output_txt,
    'flaky-threshold=f'=> \$flaky_thresh,
    'help'             => \$help,
) or die "Error in command line arguments\n";

if ($help) {
    print "Usage: $0 [--input-dir DIR] [--output-csv FILE] [--output-txt FILE] [--flaky-threshold F]\n";
    print "  Aggregates JUnit XML test results from multiple CI runs.\n";
    exit 0;
}

my %test_results;   # test_name => { pass => N, fail => N, skip => N, errors => [], durations => [] }
my $total_files = 0;

# Discover all JUnit XML files
my @xml_files;
find(sub { push @xml_files, $File::Find::name if /\.xml$/i }, $input_dir);

die "No XML files found in $input_dir\n" unless @xml_files;

for my $file (@xml_files) {
    $total_files++;
    parse_junit_xml($file);
}

# Calculate statistics and identify flaky tests
my @flaky_tests;
my @always_fail;
my ($global_pass, $global_fail, $global_skip) = (0, 0, 0);

for my $test (sort keys %test_results) {
    my $r = $test_results{$test};
    my $total_runs = ($r->{pass} || 0) + ($r->{fail} || 0) + ($r->{skip} || 0);
    next unless $total_runs > 0;

    my $pass_rate = $total_runs > 0 ? $r->{pass} / $total_runs : 0;
    $r->{pass_rate} = $pass_rate;
    $r->{total_runs} = $total_runs;

    $global_pass += $r->{pass};
    $global_fail += $r->{fail};
    $global_skip += $r->{skip};

    if ($pass_rate > $flaky_thresh && $pass_rate < (1.0 - $flaky_thresh)) {
        push @flaky_tests, $test;
    }
    if ($pass_rate == 0 && $r->{fail} > 0) {
        push @always_fail, $test;
    }
}

# Write CSV report
open my $csv_fh, '>', $output_csv or die "Cannot open $output_csv: $!\n";
print $csv_fh "test_name,pass,fail,skip,total_runs,pass_rate,avg_duration_s,flaky\n";
for my $test (sort keys %test_results) {
    my $r = $test_results{$test};
    my $avg_dur = 0;
    if ($r->{durations} && @{$r->{durations}}) {
        my $sum = 0;
        $sum += $_ for @{$r->{durations}};
        $avg_dur = $sum / scalar(@{$r->{durations}});
    }
    my $is_flaky = (grep { $_ eq $test } @flaky_tests) ? 'YES' : 'NO';
    printf $csv_fh "%s,%d,%d,%d,%d,%.2f,%.3f,%s\n",
        $test, $r->{pass}||0, $r->{fail}||0, $r->{skip}||0,
        $r->{total_runs}||0, ($r->{pass_rate}||0)*100, $avg_dur, $is_flaky;
}
close $csv_fh;

# Write text summary
my $timestamp = strftime("%Y-%m-%d %H:%M:%S", localtime);
open my $txt_fh, '>', $output_txt or die "Cannot open $output_txt: $!\n";
print $txt_fh "=" x 70, "\n";
print $txt_fh "  mmWave Firmware CI - Aggregated Test Results\n";
print $txt_fh "  Generated: $timestamp\n";
print $txt_fh "=" x 70, "\n\n";
printf $txt_fh "Files processed:  %d\n", $total_files;
printf $txt_fh "Unique tests:     %d\n", scalar keys %test_results;
printf $txt_fh "Total PASS:       %d\n", $global_pass;
printf $txt_fh "Total FAIL:       %d\n", $global_fail;
printf $txt_fh "Total SKIP:       %d\n", $global_skip;
my $global_total = $global_pass + $global_fail + $global_skip;
printf $txt_fh "Overall pass rate: %.1f%%\n\n", $global_total > 0 ? ($global_pass/$global_total)*100 : 0;

if (@flaky_tests) {
    print $txt_fh "FLAKY TESTS (inconsistent results across runs):\n";
    for my $t (@flaky_tests) {
        printf $txt_fh "  - %-50s  pass_rate=%.1f%%\n", $t, ($test_results{$t}{pass_rate}||0)*100;
    }
    print $txt_fh "\n";
}

if (@always_fail) {
    print $txt_fh "ALWAYS FAILING TESTS:\n";
    print $txt_fh "  - $_\n" for @always_fail;
    print $txt_fh "\n";
}

print $txt_fh "Detailed results written to: $output_csv\n";
close $txt_fh;

print "Aggregation complete. Processed $total_files files, " . scalar(keys %test_results) . " unique tests.\n";
print "Flaky tests found: " . scalar(@flaky_tests) . "\n";
print "Reports: $output_csv, $output_txt\n";

# --- Subroutines ---

sub parse_junit_xml {
    my ($file) = @_;
    open my $fh, '<', $file or do { warn "Cannot open $file: $!"; return; };
    my $content = do { local $/; <$fh> };
    close $fh;

    # Hand-parse JUnit XML to avoid dependency on XML::Simple
    while ($content =~ /<testcase\s+([^>]*)(?:\/>|>(.*?)<\/testcase>)/gs) {
        my ($attrs, $body) = ($1, $2 || '');
        my $name     = ($attrs =~ /name="([^"]*)"/)     ? $1 : 'unknown';
        my $classname= ($attrs =~ /classname="([^"]*)"/) ? $1 : '';
        my $time     = ($attrs =~ /time="([^"]*)"/)      ? $1 : 0;

        my $full_name = $classname ? "${classname}::${name}" : $name;
        $test_results{$full_name} //= { pass => 0, fail => 0, skip => 0, durations => [], errors => [] };

        if ($body =~ /<failure/s) {
            $test_results{$full_name}{fail}++;
            if ($body =~ /<failure[^>]*message="([^"]*)"/) {
                push @{$test_results{$full_name}{errors}}, $1;
            }
        } elsif ($body =~ /<skipped/s) {
            $test_results{$full_name}{skip}++;
        } else {
            $test_results{$full_name}{pass}++;
        }
        push @{$test_results{$full_name}{durations}}, $time if $time;
    }
}
