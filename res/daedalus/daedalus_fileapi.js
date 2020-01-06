
import './daedalus_util.js'

function saveBlob(blob, fileName) {
    let a = document.createElement('a');
    a.href = window.URL.createObjectURL(blob);
    a.download = fileName;
    a.dispatchEvent(new MouseEvent('click'));
}

export function downloadFile(url, headers={}, params={}, success=null, failure=null) {
    const postData = new FormData();
    const queryString = util.serializeParameters(params);

    // https://stackoverflow.com/questions/22724070/
    const xhr = new XMLHttpRequest();
    xhr.open('GET', url + queryString);

    for (let key in headers) {
        xhr.setRequestHeader(key, headers[key]);
    }

    xhr.responseType = 'blob';
    xhr.onload = function (this_, event_) {
        let blob = this_.target.response;

        if (!blob || this_.target.status != 200) {
            if (failure !== null) {
                failure({status: this_.target.status, blob})
            }
        } else {
            // expect the reply from the server to have a header
            // set indicating the name of the resource file
            let contentDispo = xhr.getResponseHeader('Content-Disposition');
            console.log(xhr)

            let fileName;
            // https://stackoverflow.com/a/23054920/
            if (contentDispo !== null) {
                // this string can contain multiple semi-colon separated parts
                // one of those parts could be be 'filename=name;'
                fileName = contentDispo.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)[1];
            }

            if (!fileName) {
                // guess the name from the url or choose a default name
                console.error("filename not found in xhr request header 'Content-Disposition'")
                let parts;
                parts = xhr.responseURL.split('/')
                parts = parts[parts.length-1].split('?')

                fileName = parts[0] || 'resource.bin'
            }
            saveBlob(blob, fileName);
            if (success !== null) {
                success({url, fileName, blob})
            }
        }
    }
    xhr.send(postData);
}


function _uploadFileImpl(elem, urlbase, headers={}, params={}, success=null, failure=null, progress=null) {

    let queryString = util.serializeParameters(params);

    let arrayLength = elem.files.length;

    for (let i = 0; i < arrayLength; i++) {
        let file = elem.files[i];

        let url;
        if (urlbase.endsWith('/')) {
            url = urlbase + file.name
        } else {
            url = urlbase + '/' + file.name
        }

        url += queryString

        let xhr = new XMLHttpRequest();
        xhr.open('POST', url, true);


        for (let key in headers) {
            xhr.setRequestHeader(key, headers[key]);
        }

        xhr.upload.onprogress = function(event) {
            if (event.lengthComputable) {
                if (progress !== null) {
                    progress({
                        bytesTransfered: event.loaded,
                        fileSize: file.size,
                        fileName: file.name,
                        finished: false,
                    })
                }
            }
        }

        xhr.onreadystatechange = function() {
            if (xhr.readyState == 4 && xhr.status == 200) {
                if (success !== null) {
                    let params={name: file.name, url,
                        lastModified: file.lastModified,
                        size: file.size, type: file.type};
                    success(params)
                    if (progress !== null) {
                        progress({
                            fileSize: file.size,
                            fileName: file.name,
                            finished: true,
                        })
                    }
                }
            } else if(xhr.status >= 400) {
                if (failure !== null) {
                    let params={name: file.name, url, status: xhr.status};
                    failure(params)
                    if (progress !== null) {
                        progress({
                            fileSize: file.size,
                            fileName: file.name,
                            finished: true,
                        })
                    }
                }
            } else {
                console.log("xhr status changed: " + xhr.status)
            }
        };

        if (progress !== null) {
            progress({
                bytesTransfered: 0,
                fileSize: file.size,
                fileName: file.name,
                finished: false,
            })
        }

        let fd = new FormData();
        fd.append('upload', file);
        xhr.send(fd);
    }
}

// construct a hidden form element that allows
// a user to select files. dispatch a mouse
// event to click on this form, opening the upload file dialog
// when the user selects a file dispatch an multi-part form upload

export function uploadFile(urlbase, headers={}, params={}, success=null, failure=null, progress=null) {

    let element = document.createElement('input');
    element.type = 'file'
    element.hidden = true
    element.onchange = (event) => {_uploadFileImpl(
        element, urlbase, headers, params, success, failure, progress)}
    element.dispatchEvent(new MouseEvent('click'));
}