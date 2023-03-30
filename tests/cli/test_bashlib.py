from tests.base import CapturingTestCase as TestCase, main, assets, copy_of_directory

from pkg_resources import parse_version
import subprocess
import tempfile
import yaml
import json
import pytest

from ocrd.cli.bashlib import bashlib_cli

from ocrd.constants import BASHLIB_FILENAME
from ocrd_utils.constants import VERSION, MIME_TO_EXT, MIMETYPE_PAGE
from ocrd_validators.constants import BAGIT_TXT
from ocrd_models.constants import TAG_MODS_IDENTIFIER

class TestBashlibCli(TestCase):

    def invoke_bash(self, script, *args):
        # pattern input=script would not work with additional args
        with tempfile.NamedTemporaryFile() as scriptfile:
            scriptfile.write(script)
            scriptfile.close()
            result = subprocess.run(['bash', scriptfile.name] + args,
                                universal_newlines=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        return result.returncode, result.stdout, result.stderr
            
    def setUp(self):
        self.maxDiff = None
        super().setUp()

    def test_filename(self):
        exit_code, out, err = self.invoke_cli(bashlib_cli, ['filename'])
        print("out=%s\berr=%s" % (out, err))
        assert out.endswith('ocrd/lib.bash\n')

    def test_constants(self):
        def _test_constant(name, val):
            _, out, err = self.invoke_cli(bashlib_cli, ['constants', name])
            print("err=%s" % err)
            assert out == '%s\n' % val
        _test_constant('BASHLIB_FILENAME', BASHLIB_FILENAME)
        _test_constant('VERSION', VERSION)
        _test_constant('MIMETYPE_PAGE', MIMETYPE_PAGE)
        _test_constant('BAGIT_TXT', BAGIT_TXT)
        _test_constant('TAG_MODS_IDENTIFIER', TAG_MODS_IDENTIFIER)

    def test_constants_dict(self):
        _, out, err = self.invoke_cli(bashlib_cli, ['constants', 'MIME_TO_EXT'])
        assert '[image/tiff]=.tif' in out

    def test_constants_all(self):
        _, out, err = self.invoke_cli(bashlib_cli, ['constants', '*'])
        out = yaml.safe_load(out)
        assert 'VERSION' in out
        assert len(out) >= 40

    def test_constants_fail(self):
        exit_code, out, err = self.invoke_cli(bashlib_cli, ['constants', '1234!@#$--'])
        assert exit_code == 1
        assert err == "ERROR: name '1234!@#$--' is not a known constant\n"

    def test_input_files(self):
        with copy_of_directory(assets.path_to('kant_aufklaerung_1784/data')) as wsdir:
            with pushd_popd(wsdir):
                _, out, err = self.invoke_cli(bashlib_cli, ['input-files', '-I', 'OCR-D-IMG'])
                assert ("[url]='OCR-D-IMG/INPUT_0017.tif' [ID]='INPUT_0017' [mimetype]='image/tiff'"
                        "[pageId]='PHYS_0017' [outputFileId]='OUTPUT_PHYS_0017'") in out

    def test_bashlib_defs(self):
        exit_code, out, err = self.invoke_bash(
            "source $(ocrd bashlib filename) && type -t ocrd__wrap && type -t ocrd__minversion")
        assert exit_code == 0
        assert len(err) == 0
        assert 'function' in out

    def test_bashlib_minversion(self):
        exit_code, out, err = self.invoke_bash(
            "source $(ocrd bashlib filename) && ocrd__minversion 2.29.0")
        assert exit_code == 0
        version = parse_version(VERSION)
        version = "%d.%d.%d" % (version.major, version.minor+1, 0)
        exit_code, out, err = self.invoke_bash(
            "source $(ocrd bashlib filename) && ocrd__minversion " + version)
        assert exit_code > 0
        assert "ERROR: ocrd/core is too old" in err

    def test_bashlib_cp_processor(self):
        tool = {
          "executable": "ocrd-cp",
          "description": "dummy processor copying",
          "steps": ["preprocessing/optimization"],
          "categories": ["Image preprocessing"],
          "parameters": {"message": {
            "type": "string",
            "default": "",
            "description": "message to print on stdout"
          }}
        }
        script = """#!/bin/bash
        set -eu
        set -o pipefail
        MIMETYPE_PAGE=$(ocrd bashlib constants MIMETYPE_PAGE)
        source $(ocrd bashlib filename)
        ocrd__wrap ocrd-tool.json ocrd-cp "$@"
        out_file_grp=${ocrd__argv[output_file_grp]}
        message="${params[message]}"
        cd "${ocrd__argv[working_dir]}"
        mets=$(basename ${ocrd__argv[mets_file]})
        for ((n=0; n<${#ocrd__files[*]}; n++)); do
            local in_fpath=($(ocrd__input_file $n url))
            local in_id=($(ocrd__input_file $n ID))
            local in_mimetype=($(ocrd__input_file $n mimetype))
            local in_pageId=($(ocrd__input_file $n pageId))
            local out_id=$(ocrd__input_file $n outputFileId)
            local out_fpath="${ocrd__argv[output_file_grp]}/${out_id}.xml
            if ! test -f "${in_fpath#file://}"; then
                ocrd__log error "input file '${in_fpath#file://}' (ID=${in_id} pageId=${in_pageId} MIME=${in_mimetype}) is not on disk"
                continue
            fi
            if [ "x${in_mimetype}" = x${MIMETYPE_PAGE} ]; then
                ocrd__log info "processing PAGE-XML input file $in_id ($in_pageId)"
            else
                ocrd__log info "processing ${in_mimetype} input file $in_id ($in_pageId)"
            fi
            declare -a options
            if [[ "${ocrd__argv[overwrite]}" == true ]]; then
                options=( --force )
            else
                options=()
            fi
            mkdir -p $out_file_grp
            cp $options "$in_fpath" "$out_fpath"
            if [ -n "$message" ]; then
                echo "$message"
            fi
            if [ -n "$in_pageId" ]; then
                options+=( -g $in_pageId )
            fi
            options+=( -G $out_file_grp -m $in_mimetype -i "$out_id" "$out_fpath" )
            ocrd -l ${ocrd__argv[log_level]} workspace add "${options[@]}"
        done
        """
        with copy_of_directory(assets.path_to('kant_aufklaerung_1784/data')) as wsdir:
            with pushd_popd(wsdir):
                json.dump(tool, open('ocrd-tool.json'))
                exit_code, out, err = self.invoke_bash(
                    script, '-I', 'OCR-D-GT-PAGE', '-O', 'OCR-D-GT-PAGE2', '-P', 'message', 'hello world')
                assert exit_code == 0
                assert 'hello world' in out
                assert os.path.isdir('OCR-D-GT-PAGE2')

if __name__ == "__main__":
    main(__file__)

